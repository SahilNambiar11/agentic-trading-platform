"""Durable PostgreSQL state transitions for asynchronous preview jobs."""

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.orm import Session

from app.models.preview_job import PreviewJob


def create_job(
    session: Session,
    *,
    user_id: UUID,
    strategy_text: str,
    strategy_name: str | None,
    ttl_hours: int,
) -> PreviewJob:
    now = datetime.now(UTC)
    job = PreviewJob(
        id=uuid4(),
        user_id=user_id,
        status="queued",
        stage="queued",
        progress=5,
        strategy_text=strategy_text,
        strategy_name=strategy_name,
        attempt_count=0,
        created_at=now,
        expires_at=now + timedelta(hours=ttl_hours),
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def get_job(session: Session, *, job_id: UUID, user_id: UUID) -> PreviewJob | None:
    return session.scalar(
        select(PreviewJob).where(PreviewJob.id == job_id, PreviewJob.user_id == user_id)
    )


def claim_job(session: Session, job_id: UUID) -> PreviewJob | None:
    """Atomically move a queued job to running; terminal jobs cannot be reclaimed."""
    started_at = datetime.now(UTC)
    result = session.execute(
        update(PreviewJob)
        .where(PreviewJob.id == job_id, PreviewJob.status == "queued")
        .values(
            status="running",
            stage="parsing",
            progress=20,
            started_at=started_at,
            attempt_count=PreviewJob.attempt_count + 1,
        )
    )
    session.commit()
    if cast(CursorResult[object], result).rowcount != 1:
        return None
    return session.get(PreviewJob, job_id)


def update_progress(session: Session, job: PreviewJob, *, stage: str, progress: int) -> None:
    job.stage = stage
    job.progress = progress
    session.commit()


def complete_job(session: Session, job: PreviewJob, result: dict[str, object]) -> None:
    job.status = "completed"
    job.stage = "completed"
    job.progress = 100
    job.preview_result = result
    job.completed_at = datetime.now(UTC)
    session.commit()


def fail_job(session: Session, job: PreviewJob, error: str) -> None:
    job.status = "failed"
    job.stage = "failed"
    job.progress = 100
    job.error_message = error
    job.completed_at = datetime.now(UTC)
    session.commit()


def delete_expired_jobs(session: Session, *, now: datetime | None = None) -> int:
    """Delete expired preview state and return the affected row count."""
    result = session.execute(
        delete(PreviewJob).where(PreviewJob.expires_at < (now or datetime.now(UTC)))
    )
    session.commit()
    return cast(CursorResult[object], result).rowcount or 0
