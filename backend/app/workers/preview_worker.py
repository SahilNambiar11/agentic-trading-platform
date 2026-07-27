"""RQ task that runs an already-queued strategy preview."""

import logging
from types import TracebackType
from typing import cast
from uuid import UUID

from redis import Redis
from rq import get_current_job
from rq.job import Job
from sqlalchemy.exc import DisconnectionError, OperationalError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.job_store import (
    acquire_preview_job_lock,
    release_preview_job_lock,
    transition_job_after_operational_failure,
)
from app.services.preview_job_service import TransientPreviewJobError, run_preview_job
from app.services.strategy_parser import OpenAIStrategyParser

logger = logging.getLogger(__name__)
TRANSIENT_DATABASE_ERRORS = (OperationalError, SQLAlchemyTimeoutError, DisconnectionError)


def process_preview_job(
    job_id: str,
    user_id: str,
    strategy_text: str,
    strategy_name: str | None,
) -> None:
    """Process one minimal queue payload; PostgreSQL remains the source of truth."""
    del user_id, strategy_text, strategy_name
    try:
        preview_job_id = UUID(job_id)
    except ValueError:
        logger.error("RQ preview payload contains an invalid job identifier")
        return

    with SessionLocal() as session:
        acquired = False
        try:
            settings = get_settings()
            acquired = acquire_preview_job_lock(
                session,
                preview_job_id,
                timeout_seconds=settings.preview_job_lock_wait_seconds,
            )
            if not acquired:
                logger.warning(
                    "Skipped duplicate concurrent preview execution",
                    extra={
                        "event": "preview_lock",
                        "component": "worker",
                        "job_id": str(preview_job_id),
                        "queue": settings.preview_queue_name,
                        "outcome": "timeout",
                    },
                )
                return

            rq_job = get_current_job()
            retries_left = rq_job.retries_left if rq_job is not None else None
            allow_running_retry = (
                retries_left is not None and retries_left < settings.preview_job_max_retries
            )
            run_preview_job(
                session,
                job_id=preview_job_id,
                parser=OpenAIStrategyParser.from_settings(),
                allow_running_retry=allow_running_retry,
            )
        except TRANSIENT_DATABASE_ERRORS as error:
            session.rollback()
            logger.exception(
                "Transient database failure while executing preview job %s",
                preview_job_id,
            )
            raise TransientPreviewJobError("Transient preview job operation failed.") from error
        except TransientPreviewJobError:
            raise
        except Exception as error:
            session.rollback()
            logger.exception(
                "Unexpected worker failure for preview job %s: %s",
                preview_job_id,
                type(error).__name__,
            )
            try:
                transition_job_after_operational_failure(
                    session,
                    job_id=preview_job_id,
                    will_retry=False,
                )
            except TRANSIENT_DATABASE_ERRORS as persistence_error:
                session.rollback()
                raise TransientPreviewJobError(
                    "Transient preview job operation failed."
                ) from persistence_error
            except Exception:
                session.rollback()
                logger.exception(
                    "Unable to persist terminal preview failure for job %s",
                    preview_job_id,
                )
        finally:
            if acquired:
                try:
                    session.rollback()
                    release_preview_job_lock(session, preview_job_id)
                except Exception:
                    session.invalidate()
                    logger.exception(
                        "Unable to release preview advisory lock",
                        extra={
                            "event": "preview_lock",
                            "component": "worker",
                            "job_id": str(preview_job_id),
                            "queue": get_settings().preview_queue_name,
                            "outcome": "release_failed",
                        },
                    )


def handle_preview_job_failure(
    job: Job,
    connection: Redis,
    exception_type: type[BaseException],
    exception_value: BaseException,
    traceback: TracebackType | None,
) -> None:
    """Synchronize PostgreSQL before RQ schedules a retry or final failure."""
    del connection, exception_value, traceback
    raw_args = job.args  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    args = cast(list[object] | tuple[object, ...], raw_args)
    try:
        preview_job_id = UUID(str(args[0]))
    except (IndexError, TypeError, ValueError):
        logger.error(
            "Unable to synchronize failed RQ job %s with an invalid preview payload",
            job.id,
        )
        return

    retries_left = job.retries_left or 0
    will_retry = retries_left > 0
    with SessionLocal() as session:
        changed = transition_job_after_operational_failure(
            session,
            job_id=preview_job_id,
            will_retry=will_retry,
        )
    logger.error(
        "RQ preview execution failed",
        extra={
            "event": "preview_job_transition",
            "component": "worker",
            "job_id": str(preview_job_id),
            "queue": get_settings().preview_queue_name,
            "previous_status": "running",
            "new_status": "queued" if will_retry else "failed",
            "attempt": get_settings().preview_job_max_retries - retries_left + 1,
            "max_attempts": get_settings().preview_job_max_retries + 1,
            "outcome": (
                f"{exception_type.__name__}:state_changed"
                if changed
                else f"{exception_type.__name__}:state_unchanged"
            ),
        },
    )
