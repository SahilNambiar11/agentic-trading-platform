from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    DateTime,
    FetchedValue,
    ForeignKey,
    Index,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

strategy_json_type = JSON().with_variant(JSONB(), "postgresql")

# Supabase owns this table; registering it lets SQLAlchemy resolve the FK during flushes.
auth_users_table = Table(
    "users",
    Base.metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    schema="auth",
)


class Strategy(Base):
    """SQLAlchemy ORM mapping for `public.strategies`.

    A Strategy stores the user's original natural-language idea plus optional
    parsed JSON. The parsed JSON is nullable because the current app can save a
    draft strategy before LLM parsing/backtesting exists.
    """

    __tablename__ = "strategies"
    __table_args__ = (
        CheckConstraint(
            "char_length(name) between 1 and 200",
            name="strategies_name_length_check",
        ),
        CheckConstraint(
            "char_length(source_text) > 0",
            name="strategies_source_text_length_check",
        ),
        UniqueConstraint("id", "user_id", name="strategies_id_user_id_key"),
        Index("strategies_user_id_idx", "user_id"),
        {"schema": "public"},
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        nullable=False,
        server_default=text("auth.uid()"),
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    strategy_json: Mapped[dict[str, Any] | None] = mapped_column(
        strategy_json_type,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        server_onupdate=FetchedValue(),
    )
