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
from app.queue.connection import get_preview_queue
from app.queue.preview_queue import PreviewQueue
from app.schemas.jobs import PreviewEnqueueResponse
from app.schemas.strategy import (
    ConfirmedStrategySaveRequest,
    StrategyCreate,
    StrategyPreviewRequest,
    StrategyResponse,
    StrategyUpdate,
)
from app.schemas.strategy_spec import ParsedStrategyResult
from app.services.preview_job_service import submit_preview_job
from app.services.strategy_interpretation import interpret_strategy
from app.services.strategy_semantics import StrategyValidationError, validate_strategy_semantics

router = APIRouter(prefix="/strategies", tags=["strategies"])
DatabaseSession = Annotated[Session, Depends(get_db_session)]


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


@router.post(
    "/preview",
    response_model=PreviewEnqueueResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def preview_strategy(
    payload: StrategyPreviewRequest,
    current_user: CurrentUser,
    session: DatabaseSession,
    queue: Annotated[PreviewQueue, Depends(get_preview_queue)],
) -> PreviewEnqueueResponse:
    """Persist and enqueue a preview job without running the pipeline inline."""
    try:
        job_id = submit_preview_job(
            session, queue, user_id=current_user.id, strategy_text=payload.text
        )
        return PreviewEnqueueResponse(job_id=job_id)
    except Exception as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to queue the strategy preview.",
        ) from exc


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
