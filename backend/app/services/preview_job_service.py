"""Application workflow for durable asynchronous preview jobs."""

import logging
from collections.abc import Callable
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.exc import DisconnectionError, OperationalError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.orm import Session

from app.backtesting.strategy_compiler import StrategyCompilationError
from app.core.config import get_settings
from app.models.preview_job import PreviewJob
from app.queue.preview_queue import PreviewQueue
from app.schemas.strategy_spec import ParsedStrategyResult
from app.services.job_store import (
    acquire_preview_job_lock,
    claim_job,
    complete_job,
    create_job,
    fail_job,
    release_preview_job_lock,
    transition_job_after_operational_failure,
    update_progress,
)
from app.services.strategy_parser import (
    StrategyParser,
    StrategyParserError,
    StrategyProviderTimeoutError,
)
from app.services.strategy_preview import (
    STARTING_CASH,
    MarketDataUnavailableError,
    StrategyPreview,
    create_preview,
)
from app.services.strategy_semantics import StrategyValidationError

logger = logging.getLogger(__name__)
PreviewFactory = Callable[[Session, ParsedStrategyResult], StrategyPreview]
TRANSIENT_DATABASE_ERRORS = (OperationalError, SQLAlchemyTimeoutError, DisconnectionError)


class TransientPreviewJobError(RuntimeError):
    """An operational failure that is safe for RQ to retry."""


def submit_preview_job(
    session: Session,
    queue: PreviewQueue,
    *,
    user_id: UUID,
    strategy_text: str,
    strategy_name: str | None = None,
) -> UUID:
    """Persist first, then hand the minimal payload to the queue."""
    settings = get_settings()
    job_id = uuid4()
    acquired = acquire_preview_job_lock(
        session,
        job_id,
        timeout_seconds=settings.preview_job_lock_wait_seconds,
    )
    if not acquired:
        logger.error(
            "Timed out acquiring the preview submission lock",
            extra={
                "event": "preview_submission_lock",
                "component": "api",
                "job_id": str(job_id),
                "queue": settings.preview_queue_name,
                "outcome": "timeout",
            },
        )
        raise RuntimeError("Unable to safely submit the preview job.")

    try:
        job = create_job(
            session,
            job_id=job_id,
            user_id=user_id,
            strategy_text=strategy_text,
            strategy_name=strategy_name,
            ttl_hours=settings.preview_job_ttl_hours,
        )
        try:
            queue.enqueue(
                job_id=job.id,
                user_id=user_id,
                strategy_text=strategy_text,
                strategy_name=strategy_name,
            )
        except Exception:
            logger.exception(
                "Unable to enqueue preview job",
                extra={
                    "event": "preview_enqueue",
                    "component": "api",
                    "job_id": str(job.id),
                    "queue": settings.preview_queue_name,
                    "outcome": "failed",
                },
            )
            fail_job(session, job, "Unable to queue the strategy preview.")
            raise
        logger.info(
            "Preview job submitted",
            extra={
                "event": "preview_enqueue",
                "component": "api",
                "job_id": str(job.id),
                "queue": settings.preview_queue_name,
                "previous_status": "queued",
                "new_status": "queued",
                "outcome": "success",
            },
        )
        return job.id
    finally:
        try:
            session.rollback()
            release_preview_job_lock(session, job_id)
        except Exception:
            session.invalidate()
            logger.exception(
                "Unable to release preview submission lock",
                extra={
                    "event": "preview_submission_lock",
                    "component": "api",
                    "job_id": str(job_id),
                    "queue": settings.preview_queue_name,
                    "outcome": "release_failed",
                },
            )


def run_preview_job(
    session: Session,
    *,
    job_id: UUID,
    parser: StrategyParser,
    preview_factory: PreviewFactory = create_preview,
    allow_running_retry: bool = False,
) -> bool:
    """Claim and execute one queued job, returning false when it was ineligible."""
    job: PreviewJob | None = None
    try:
        job = claim_job(session, job_id, allow_running_retry=allow_running_retry)
        if job is None:
            return False

        parsed = parser.parse(job.strategy_text)
        update_progress(session, job, stage="validating", progress=35)
        update_progress(session, job, stage="compiling", progress=50)
        update_progress(session, job, stage="loading_data", progress=70)
        update_progress(session, job, stage="backtesting", progress=85)
        preview = preview_factory(session, parsed)
        update_progress(session, job, stage="generating_results", progress=95)
        complete_job(session, job, serialize_preview(parsed, preview))
    except (StrategyValidationError, StrategyCompilationError, MarketDataUnavailableError) as error:
        logger.info("Preview job %s rejected: %s: %s", job_id, type(error).__name__, error)
        assert job is not None
        persist_failure(session, job, str(error))
    except StrategyProviderTimeoutError as error:
        raise_transient_failure(session, job_id, error)
    except StrategyParserError as error:
        logger.info("Preview job %s parser failure: %s: %s", job_id, type(error).__name__, error)
        assert job is not None
        persist_failure(session, job, "Unable to parse the strategy.")
    except TRANSIENT_DATABASE_ERRORS as error:
        raise_transient_failure(session, job_id, error)
    except Exception as error:
        logger.exception("Preview job %s failed: %s", job_id, type(error).__name__)
        if job is None:
            session.rollback()
            transition_job_after_operational_failure(
                session,
                job_id=job_id,
                will_retry=False,
            )
        else:
            persist_failure(session, job, "Unable to complete the strategy preview.")
    return True


def persist_failure(session: Session, job: PreviewJob, message: str) -> None:
    """Persist a safe terminal error, retrying only if PostgreSQL is unavailable."""
    try:
        fail_job(session, job, message)
    except TRANSIENT_DATABASE_ERRORS as error:
        raise_transient_failure(session, job.id, error)


def raise_transient_failure(
    session: Session,
    job_id: UUID | None,
    error: Exception,
) -> None:
    session.rollback()
    logger.exception(
        "Transient preview job failure; RQ may retry job %s: %s",
        job_id,
        type(error).__name__,
    )
    raise TransientPreviewJobError("Transient preview job operation failed.") from error


def optional_decimal(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def serialize_preview(
    parsed: ParsedStrategyResult,
    preview: StrategyPreview,
) -> dict[str, object]:
    """Serialize deterministic preview output without provider internals."""
    return {
        "parsed_strategy": {
            "specification": parsed.specification.model_dump(mode="json"),
            "defaults_applied": [item.model_dump(mode="json") for item in parsed.defaults_applied],
            "assumptions": [item.model_dump(mode="json") for item in parsed.assumptions],
            "requires_confirmation": parsed.requires_confirmation,
            "original_text": parsed.original_text,
            "interpretation": preview.interpretation,
        },
        "backtest": {
            "symbol": parsed.specification.symbol,
            "interval": parsed.specification.interval,
            "start_date": preview.start_timestamp.isoformat(),
            "end_date": preview.end_timestamp.isoformat(),
            "bar_count": preview.bar_count,
            "starting_cash": str(STARTING_CASH),
            "ending_value": str(preview.execution.final_portfolio_value),
            "total_return_percent": str(preview.metrics.total_return_percentage),
            "cagr_percent": optional_decimal(preview.metrics.cagr_percentage),
            "max_drawdown_percent": str(preview.metrics.maximum_drawdown_percentage),
            "trade_count": len(preview.execution.completed_trades),
            "win_rate_percent": str(preview.metrics.win_rate_percentage),
            "buy_and_hold_return_percent": str(preview.metrics.buy_and_hold_return_percentage),
            "equity_curve": [
                {
                    "timestamp": point.timestamp.isoformat(),
                    "strategy_value": str(point.equity),
                    "buy_and_hold_value": str(benchmark.equity),
                }
                for point, benchmark in zip(
                    preview.execution.equity_curve[preview.comparison_start_index :],
                    preview.buy_and_hold_equity_curve,
                    strict=True,
                )
            ],
            "price_series": [
                {
                    "timestamp": bar.timestamp.isoformat(),
                    "close_price": str(bar.close_price),
                }
                for bar in preview.bars
            ],
            "trades": [
                {
                    "signal_timestamp": trade.signal_timestamp.isoformat(),
                    "entry_timestamp": trade.entry_timestamp.isoformat(),
                    "entry_price": str(trade.entry_price),
                    "quantity": trade.quantity,
                    "exit_signal_timestamp": (
                        trade.exit_signal_timestamp.isoformat()
                        if trade.exit_signal_timestamp is not None
                        else None
                    ),
                    "exit_timestamp": trade.exit_timestamp.isoformat(),
                    "exit_price": str(trade.exit_price),
                    "profit_loss": str(trade.profit_loss),
                    "return_percentage": str(trade.return_percentage),
                    "exit_reason": trade.exit_reason,
                }
                for trade in preview.execution.completed_trades
            ],
        },
    }
