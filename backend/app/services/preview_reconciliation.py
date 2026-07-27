"""Bounded PostgreSQL/RQ reconciliation for durable preview jobs."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.preview_job import PreviewJob
from app.queue.preview_queue import PreviewQueue
from app.services.job_store import (
    list_reconciliation_candidates,
    release_preview_job_lock,
    transition_job_after_operational_failure,
    try_acquire_preview_job_lock,
)

logger = logging.getLogger(__name__)
LockAcquirer = Callable[[Session, UUID], bool]
LockReleaser = Callable[[Session, UUID], None]
RECOVERY_FAILURE_MESSAGE = "Unable to recover the strategy preview. Run the preview again."


@dataclass
class ReconciliationSummary:
    scanned: int = 0
    active: int = 0
    recovered: int = 0
    failed: int = 0
    locked: int = 0
    not_stale: int = 0
    state_changed: int = 0


def reconcile_preview_jobs(
    session: Session,
    queue: PreviewQueue,
    *,
    max_retries: int,
    stale_after_seconds: int,
    batch_size: int,
    registry_scan_limit: int,
    now: datetime | None = None,
    acquire_lock: LockAcquirer = try_acquire_preview_job_lock,
    release_lock: LockReleaser = release_preview_job_lock,
) -> ReconciliationSummary:
    """Reconcile one bounded batch without duplicating active RQ jobs."""
    started = monotonic()
    current_time = now or datetime.now(UTC)
    max_attempts = max_retries + 1
    active_ids = queue.active_preview_job_ids(scan_limit=registry_scan_limit)
    candidates = list_reconciliation_candidates(session, limit=batch_size)
    summary = ReconciliationSummary(scanned=len(candidates))

    for job in candidates:
        if job.id in active_ids:
            summary.active += 1
            log_action(job, "active", job.status, job.status, max_attempts)
            continue

        exhausted = job.attempt_count >= max_attempts
        expired = comparable_time(current_time, job.expires_at) >= job.expires_at
        stale = job.status == "running" and is_stale(
            current_time,
            job.started_at,
            stale_after_seconds,
        )
        if job.status == "running" and not stale and not exhausted and not expired:
            summary.not_stale += 1
            log_action(job, "awaiting_active_state", job.status, job.status, max_attempts)
            continue

        if not acquire_lock(session, job.id):
            summary.locked += 1
            log_action(job, "lock_held", job.status, job.status, max_attempts)
            continue

        try:
            session.refresh(job)
            if job.status not in {"queued", "running"}:
                summary.state_changed += 1
                log_action(job, "terminal_state", job.status, job.status, max_attempts)
                continue

            active_ids = queue.active_preview_job_ids(scan_limit=registry_scan_limit)
            if job.id in active_ids:
                summary.active += 1
                log_action(job, "active_after_lock", job.status, job.status, max_attempts)
                continue

            previous_status = job.status
            exhausted = job.attempt_count >= max_attempts
            expired = comparable_time(current_time, job.expires_at) >= job.expires_at
            stale = job.status == "running" and is_stale(
                current_time,
                job.started_at,
                stale_after_seconds,
            )

            if exhausted or expired:
                changed = transition_job_after_operational_failure(
                    session,
                    job_id=job.id,
                    will_retry=False,
                    final_error=RECOVERY_FAILURE_MESSAGE,
                )
                if changed:
                    summary.failed += 1
                log_action(job, "failed_exhausted", previous_status, "failed", max_attempts)
                continue

            if job.status == "running" and not stale:
                summary.not_stale += 1
                log_action(
                    job,
                    "awaiting_active_state_after_lock",
                    previous_status,
                    previous_status,
                    max_attempts,
                )
                continue

            if job.status == "running":
                transition_job_after_operational_failure(
                    session,
                    job_id=job.id,
                    will_retry=True,
                )
                session.refresh(job)

            queue.enqueue(
                job_id=job.id,
                user_id=job.user_id,
                strategy_text=job.strategy_text,
                strategy_name=job.strategy_name,
                retry_count=max_retries - job.attempt_count,
            )
            active_ids.add(job.id)
            summary.recovered += 1
            log_action(job, "re_enqueued", previous_status, "queued", max_attempts)
        finally:
            try:
                session.rollback()
                release_lock(session, job.id)
            except Exception:
                session.invalidate()
                logger.exception(
                    "Unable to release preview reconciliation lock",
                    extra={
                        "event": "preview_reconciliation_lock",
                        "component": "worker",
                        "job_id": str(job.id),
                        "queue": "preview",
                        "outcome": "release_failed",
                    },
                )
                raise

    logger.info(
        "Preview reconciliation completed",
        extra={
            "event": "reconciliation_completed",
            "component": "worker",
            "queue": "preview",
            "outcome": "success",
            "duration_ms": round((monotonic() - started) * 1000, 2),
        },
    )
    return summary


def comparable_time(reference: datetime, value: datetime) -> datetime:
    if value.tzinfo is None:
        return reference.replace(tzinfo=None)
    return reference


def is_stale(
    now: datetime,
    started_at: datetime | None,
    stale_after_seconds: int,
) -> bool:
    if started_at is None:
        return True
    return (comparable_time(now, started_at) - started_at).total_seconds() >= stale_after_seconds


def log_action(
    job: PreviewJob,
    action: str,
    previous_status: str,
    new_status: str,
    max_attempts: int,
) -> None:
    logger.info(
        "Preview reconciliation action",
        extra={
            "event": "preview_reconciliation",
            "component": "worker",
            "job_id": str(job.id),
            "queue": "preview",
            "previous_status": previous_status,
            "new_status": new_status,
            "reconciliation_action": action,
            "attempt": job.attempt_count,
            "max_attempts": max_attempts,
        },
    )
