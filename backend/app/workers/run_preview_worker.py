"""Production-capable entrypoint for the preview RQ worker."""

import argparse
import logging

from rq import Queue, SimpleWorker, Worker

from app.core import operations
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.queue.connection import get_preview_queue, get_redis_connection
from app.services.preview_reconciliation import reconcile_preview_jobs

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the preview RQ worker.")
    parser.add_argument(
        "--simple-worker",
        action="store_true",
        help="Use RQ SimpleWorker for local environments where forking is unsuitable.",
    )
    return parser


def run(*, simple_worker: bool = False) -> int:
    """Validate dependencies, reconcile durable state, then consume preview jobs."""
    settings = get_settings()
    configure_logging(settings.log_level)
    redis_connection = get_redis_connection()
    queue = get_preview_queue()
    worker_class = SimpleWorker if simple_worker else Worker

    logger.info(
        "Preview worker startup validation started",
        extra={
            "event": "startup",
            "component": "worker",
            "queue": settings.preview_queue_name,
            "outcome": "started",
        },
    )
    try:
        operations.validate_dependencies(redis_connection=redis_connection)
        with SessionLocal() as session:
            summary = reconcile_preview_jobs(
                session,
                queue,
                max_retries=settings.preview_job_max_retries,
                stale_after_seconds=settings.preview_job_stale_after_seconds,
                batch_size=settings.preview_job_reconciliation_batch_size,
                registry_scan_limit=settings.preview_job_registry_scan_limit,
            )
        logger.info(
            "Preview worker reconciliation completed",
            extra={
                "event": "startup_reconciliation",
                "component": "worker",
                "queue": settings.preview_queue_name,
                "outcome": "success",
                "reconciliation_scanned": summary.scanned,
                "reconciliation_recovered": summary.recovered,
                "reconciliation_failed": summary.failed,
            },
        )

        rq_queue = Queue(settings.preview_queue_name, connection=redis_connection)
        worker = worker_class(
            [rq_queue],
            connection=redis_connection,
            log_job_description=False,
        )
        logger.info(
            "Preview worker listening",
            extra={
                "event": "worker_listening",
                "component": "worker",
                "queue": settings.preview_queue_name,
                "outcome": "ready",
            },
        )
        worker.work(
            with_scheduler=True,
            logging_level=settings.log_level,
        )
        return 0
    except Exception:
        logger.exception(
            "Preview worker startup or execution failed",
            extra={
                "event": "worker_failure",
                "component": "worker",
                "queue": settings.preview_queue_name,
                "outcome": "failed",
            },
        )
        return 1
    finally:
        operations.dispose_resources(redis_connection=redis_connection)
        logger.info(
            "Preview worker shutdown completed",
            extra={
                "event": "shutdown",
                "component": "worker",
                "queue": settings.preview_queue_name,
                "outcome": "success",
            },
        )


def main() -> int:
    arguments = build_parser().parse_args()
    return run(simple_worker=arguments.simple_worker)


if __name__ == "__main__":
    raise SystemExit(main())
