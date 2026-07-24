from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.backtesting.strategy_compiler import StrategyCompilationError, compile_strategy
from app.db.session import get_db_session
from app.models.strategy import Strategy
from app.schemas.strategy import (
    BacktestPreviewResponse,
    ConfirmedStrategySaveRequest,
    ParsedStrategyReview,
    StrategyCreate,
    StrategyPreviewRequest,
    StrategyPreviewResponse,
    StrategyResponse,
    StrategyUpdate,
)
from app.schemas.strategy_spec import ParsedStrategyResult
from app.services.strategy_interpretation import interpret_strategy
from app.services.strategy_parser import (
    OpenAIStrategyParser,
    StrategyParser,
    StrategyParserError,
    StrategyProviderError,
)
from app.services.strategy_preview import (
    STARTING_CASH,
    MarketDataUnavailableError,
    create_preview,
)
from app.services.strategy_semantics import StrategyValidationError, validate_strategy_semantics

router = APIRouter(prefix="/strategies", tags=["strategies"])
DatabaseSession = Annotated[Session, Depends(get_db_session)]


def get_strategy_parser() -> StrategyParser:
    return OpenAIStrategyParser.from_settings()


ParserDependency = Annotated[StrategyParser, Depends(get_strategy_parser)]


def get_owned_strategy(session: Session, strategy_id: UUID, user_id: UUID) -> Strategy:
    """Fetch one strategy only if it belongs to the authenticated user."""
    try:
        strategy = session.scalar(
            select(Strategy).where(
                Strategy.id == strategy_id,
                Strategy.user_id == user_id,
            )
        )
    except SQLAlchemyError as exc:
        session.rollback()
        raise database_error() from exc

    if strategy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found.",
        )
    return strategy


def database_error() -> HTTPException:
    """Hide internal database details behind a stable API error message."""
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unable to complete the strategy database operation.",
    )


def commit_and_refresh(session: Session, strategy: Strategy) -> None:
    """Commit a strategy change and reload database-generated fields."""
    try:
        session.commit()
        session.refresh(strategy)
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Strategy violates a database constraint.",
        ) from exc
    except SQLAlchemyError as exc:
        session.rollback()
        raise database_error() from exc


@router.post("/preview", response_model=StrategyPreviewResponse)
def preview_strategy(
    payload: StrategyPreviewRequest,
    current_user: CurrentUser,
    session: DatabaseSession,
    parser: ParserDependency,
) -> StrategyPreviewResponse:
    """Parse and backtest without creating any database record."""
    del current_user  # Authentication is required even though preview has no owner-scoped write.
    try:
        parsed = parser.parse(payload.text)
        preview = create_preview(session, parsed)
    except StrategyValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except MarketDataUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except StrategyCompilationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except StrategyProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The strategy parser is temporarily unavailable. Please try again.",
        ) from exc
    except StrategyParserError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return StrategyPreviewResponse(
        parsed_strategy=ParsedStrategyReview.from_parsed_result(parsed, preview.interpretation),
        backtest=BacktestPreviewResponse(
            symbol=parsed.specification.symbol,
            interval=parsed.specification.interval,
            start_date=preview.start_timestamp,
            end_date=preview.end_timestamp,
            bar_count=preview.bar_count,
            starting_cash=STARTING_CASH,
            ending_value=preview.execution.final_portfolio_value,
            total_return_percent=preview.metrics.total_return_percentage,
            cagr_percent=preview.metrics.cagr_percentage,
            max_drawdown_percent=preview.metrics.maximum_drawdown_percentage,
            trade_count=len(preview.execution.completed_trades),
            win_rate_percent=preview.metrics.win_rate_percentage,
            buy_and_hold_return_percent=preview.metrics.buy_and_hold_return_percentage,
        ),
    )


@router.post("/confirmed", response_model=StrategyResponse, status_code=status.HTTP_201_CREATED)
def save_confirmed_strategy(
    payload: ConfirmedStrategySaveRequest,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> Strategy:
    """Persist a browser-submitted strategy only after strict revalidation."""
    try:
        validate_strategy_semantics(payload.specification)
        # Compilation is a second, code-only validation pass; it makes no provider call.
        compile_strategy(payload.specification)
    except (StrategyValidationError, StrategyCompilationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    parsed = ParsedStrategyResult(
        specification=payload.specification,
        defaults_applied=payload.defaults_applied,
        assumptions=payload.assumptions,
        requires_confirmation=payload.requires_confirmation,
        original_text=payload.source_text,
    )
    strategy = Strategy(
        user_id=current_user.id,
        name=payload.name,
        source_text=payload.source_text,
        strategy_json={
            "specification": payload.specification.model_dump(mode="json"),
            "defaults_applied": [item.model_dump(mode="json") for item in payload.defaults_applied],
            "assumptions": [item.model_dump(mode="json") for item in payload.assumptions],
            "requires_confirmation": payload.requires_confirmation,
            "confirmed": True,
            "parser_version": payload.specification.version,
            "interpretation": interpret_strategy(parsed),
        },
    )
    session.add(strategy)
    commit_and_refresh(session, strategy)
    return strategy


@router.post("", response_model=StrategyResponse, status_code=status.HTTP_201_CREATED)
def create_strategy(
    payload: StrategyCreate,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> Strategy:
    """Create a strategy owned by the verified Supabase user."""
    strategy = Strategy(
        user_id=current_user.id,
        name=payload.name,
        source_text=payload.source_text,
        strategy_json=payload.strategy_json,
    )
    session.add(strategy)
    commit_and_refresh(session, strategy)
    return strategy


@router.get("", response_model=list[StrategyResponse])
def list_strategies(current_user: CurrentUser, session: DatabaseSession) -> list[Strategy]:
    """Return only the current user's strategies, newest first."""
    try:
        strategies = session.scalars(
            select(Strategy)
            .where(Strategy.user_id == current_user.id)
            .order_by(Strategy.created_at.desc(), Strategy.id.desc())
        ).all()
    except SQLAlchemyError as exc:
        session.rollback()
        raise database_error() from exc
    return list(strategies)


@router.get("/{strategy_id}", response_model=StrategyResponse)
def get_strategy(
    strategy_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> Strategy:
    """Return one current-user-owned strategy or 404 if missing/not owned."""
    return get_owned_strategy(session, strategy_id, current_user.id)


@router.patch("/{strategy_id}", response_model=StrategyResponse)
def update_strategy(
    strategy_id: UUID,
    payload: StrategyUpdate,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> Strategy:
    """Apply partial edits to a current-user-owned strategy."""
    strategy = get_owned_strategy(session, strategy_id, current_user.id)
    updates: dict[str, Any] = payload.model_dump(exclude_unset=True)
    for field_name, value in updates.items():
        setattr(strategy, field_name, value)

    commit_and_refresh(session, strategy)
    return strategy


@router.delete("/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_strategy(
    strategy_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> Response:
    """Delete a current-user-owned strategy."""
    strategy = get_owned_strategy(session, strategy_id, current_user.id)
    try:
        session.delete(strategy)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Strategy violates a database constraint.",
        ) from exc
    except SQLAlchemyError as exc:
        session.rollback()
        raise database_error() from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
