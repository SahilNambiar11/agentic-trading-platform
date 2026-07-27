"""Durable PostgreSQL state transitions for asynchronous preview jobs."""

import logging
from datetime import UTC, datetime, timedelta
from time import monotonic, sleep
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import CursorResult, delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.models.preview_job import PreviewJob

logger = logging.getLogger(__name__)


def create_job(
    session: Session,
    *,
    job_id: UUID | None = None,
    user_id: UUID,
    strategy_text: str,
    strategy_name: str | None,
    ttl_hours: int,
) -> PreviewJob:
    now = datetime.now(UTC)
    job = PreviewJob(
        id=job_id or uuid4(),
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
    log_transition(
        job,
        event="preview_job_created",
        previous_status=None,
        new_status="queued",
    )
    return job


def get_job(session: Session, *, job_id: UUID, user_id: UUID) -> PreviewJob | None:
    return session.scalar(
        select(PreviewJob).where(PreviewJob.id == job_id, PreviewJob.user_id == user_id)
    )


def claim_job(
    session: Session,
    job_id: UUID,
    *,
    allow_running_retry: bool = False,
) -> PreviewJob | None:
    """Atomically move a queued job to running; terminal jobs cannot be reclaimed."""
    started_at = datetime.now(UTC)
    eligible_status = PreviewJob.status == "queued"
    if allow_running_retry:
        eligible_status = or_(eligible_status, PreviewJob.status == "running")
    result = session.execute(
        update(PreviewJob)
        .where(PreviewJob.id == job_id, eligible_status)
        .values(
            status="running",
            stage="parsing",
            progress=20,
            started_at=started_at,
            completed_at=None,
            error_message=None,
            attempt_count=PreviewJob.attempt_count + 1,
        )
    )
    session.commit()
    if cast(CursorResult[object], result).rowcount != 1:
        return None
    job = session.get(PreviewJob, job_id)
    if job is not None:
        log_transition(
            job,
            event="preview_job_claimed",
            previous_status="queued_or_running" if allow_running_retry else "queued",
            new_status="running",
        )
    return job


def update_progress(session: Session, job: PreviewJob, *, stage: str, progress: int) -> None:
    job.stage = stage
    job.progress = progress
    session.commit()


def complete_job(session: Session, job: PreviewJob, result: dict[str, object]) -> None:
    previous_status = job.status
    job.status = "completed"
    job.stage = "completed"
    job.progress = 100
    job.preview_result = result
    job.completed_at = datetime.now(UTC)
    session.commit()
    log_transition(
        job,
        event="preview_job_completed",
        previous_status=previous_status,
        new_status="completed",
    )


def fail_job(session: Session, job: PreviewJob, error: str) -> None:
    previous_status = job.status
    job.status = "failed"
    job.stage = "failed"
    job.progress = 100
    job.error_message = error
    job.completed_at = datetime.now(UTC)
    session.commit()
    log_transition(
        job,
        event="preview_job_failed",
        previous_status=previous_status,
        new_status="failed",
    )


def transition_job_after_operational_failure(
    session: Session,
    *,
    job_id: UUID,
    will_retry: bool,
    final_error: str = "Unable to complete the strategy preview.",
) -> bool:
    """Synchronize durable state after an RQ execution failure.

    RQ invokes its failure callback before decrementing ``retries_left``. A
    retryable execution therefore returns to ``queued``; the final execution is
    persisted as a safe terminal failure.
    """
    values: dict[str, object]
    if will_retry:
        values = {
            "status": "queued",
            "stage": "queued",
            "progress": 5,
            "started_at": None,
            "completed_at": None,
            "error_message": None,
        }
    else:
        values = {
            "status": "failed",
            "stage": "failed",
            "progress": 100,
            "completed_at": datetime.now(UTC),
            "error_message": final_error,
        }

    result = session.execute(
        update(PreviewJob)
        .where(
            PreviewJob.id == job_id,
            PreviewJob.status.in_(("queued", "running")),
        )
        .values(**values)
    )
    session.commit()
    changed = cast(CursorResult[object], result).rowcount == 1
    if changed:
        job = session.get(PreviewJob, job_id)
        if job is not None:
            log_transition(
                job,
                event="preview_job_operational_transition",
                previous_status="running_or_queued",
                new_status="queued" if will_retry else "failed",
            )
    return changed


def advisory_lock_keys(job_id: UUID) -> tuple[int, int]:
    """Map a UUID to PostgreSQL's two signed 32-bit advisory-lock keys."""

    def signed(value: int) -> int:
        return value if value < 2**31 else value - 2**32

    return signed((job_id.int >> 32) & 0xFFFFFFFF), signed(job_id.int & 0xFFFFFFFF)


def try_acquire_preview_job_lock(session: Session, job_id: UUID) -> bool:
    """Prevent two workers from executing the same preview concurrently."""
    if session.get_bind().dialect.name != "postgresql":
        return True
    first_key, second_key = advisory_lock_keys(job_id)
    return bool(session.scalar(select(func.pg_try_advisory_lock(first_key, second_key))))


def acquire_preview_job_lock(
    session: Session,
    job_id: UUID,
    *,
    timeout_seconds: float,
    poll_interval_seconds: float = 0.05,
) -> bool:
    """Wait for a preview lock for a bounded duration."""
    deadline = monotonic() + timeout_seconds
    while True:
        if try_acquire_preview_job_lock(session, job_id):
            return True
        session.rollback()
        if monotonic() >= deadline:
            return False
        sleep(min(poll_interval_seconds, max(0, deadline - monotonic())))


def release_preview_job_lock(session: Session, job_id: UUID) -> None:
    """Release a preview advisory lock acquired by this database session."""
    if session.get_bind().dialect.name != "postgresql":
        return
    first_key, second_key = advisory_lock_keys(job_id)
    session.scalar(select(func.pg_advisory_unlock(first_key, second_key)))


def list_reconciliation_candidates(
    session: Session,
    *,
    limit: int,
) -> list[PreviewJob]:
    """Return a bounded, deterministic batch of nonterminal preview jobs."""
    return list(
        session.scalars(
            select(PreviewJob)
            .where(PreviewJob.status.in_(("queued", "running")))
            .order_by(PreviewJob.created_at.asc(), PreviewJob.id.asc())
            .limit(limit)
        )
    )


def log_transition(
    job: PreviewJob,
    *,
    event: str,
    previous_status: str | None,
    new_status: str,
) -> None:
    logger.info(
        "Preview job state changed",
        extra={
            "event": event,
            "component": "job_store",
            "job_id": str(job.id),
            "queue": "preview",
            "previous_status": previous_status,
            "new_status": new_status,
            "attempt": job.attempt_count,
            "outcome": "success",
        },
    )


def delete_expired_jobs(session: Session, *, now: datetime | None = None) -> int:
    """Delete expired preview state and return the affected row count."""
    result = session.execute(
        delete(PreviewJob).where(PreviewJob.expires_at < (now or datetime.now(UTC)))
    )
    session.commit()
    return cast(CursorResult[object], result).rowcount or 0
