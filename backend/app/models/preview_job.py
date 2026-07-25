from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

preview_result_type = JSON().with_variant(JSONB(), "postgresql")
preview_job_status_type = Enum(
    "queued",
    "running",
    "completed",
    "failed",
    name="preview_job_status",
    schema="public",
)
preview_job_stage_type = Enum(
    "queued",
    "parsing",
    "validating",
    "compiling",
    "loading_data",
    "backtesting",
    "generating_results",
    "completed",
    "failed",
    name="preview_job_stage",
    schema="public",
)


class PreviewJob(Base):
    """Durable state and result for one asynchronous strategy preview."""

    __tablename__ = "preview_jobs"
    __table_args__ = (
        CheckConstraint(
            "progress between 0 and 100",
            name="preview_jobs_progress_check",
        ),
        CheckConstraint(
            "char_length(strategy_text) > 0",
            name="preview_jobs_strategy_text_check",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="preview_jobs_attempt_count_check",
        ),
        Index("preview_jobs_user_id_idx", "user_id"),
        Index("preview_jobs_expires_at_idx", "expires_at"),
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
    status: Mapped[str] = mapped_column(
        preview_job_status_type,
        nullable=False,
        server_default=text("'queued'"),
    )
    stage: Mapped[str] = mapped_column(
        preview_job_stage_type,
        nullable=False,
        server_default=text("'queued'"),
    )
    progress: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("5"),
    )
    strategy_text: Mapped[str] = mapped_column(Text, nullable=False)
    strategy_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    preview_result: Mapped[dict[str, Any] | None] = mapped_column(
        preview_result_type,
        nullable=True,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
