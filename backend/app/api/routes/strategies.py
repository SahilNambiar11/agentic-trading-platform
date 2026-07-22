from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.db.session import get_db_session
from app.models.strategy import Strategy
from app.schemas.strategy import StrategyCreate, StrategyResponse, StrategyUpdate

router = APIRouter(prefix="/strategies", tags=["strategies"])
DatabaseSession = Annotated[Session, Depends(get_db_session)]


def get_owned_strategy(session: Session, strategy_id: UUID, user_id: UUID) -> Strategy:
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
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unable to complete the strategy database operation.",
    )


def commit_and_refresh(session: Session, strategy: Strategy) -> None:
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


@router.post("", response_model=StrategyResponse, status_code=status.HTTP_201_CREATED)
def create_strategy(
    payload: StrategyCreate,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> Strategy:
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
    return get_owned_strategy(session, strategy_id, current_user.id)


@router.patch("/{strategy_id}", response_model=StrategyResponse)
def update_strategy(
    strategy_id: UUID,
    payload: StrategyUpdate,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> Strategy:
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
