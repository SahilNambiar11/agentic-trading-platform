"""RQ task that runs an already-queued strategy preview."""

from uuid import UUID

from app.db.session import SessionLocal
from app.services.preview_job_service import run_preview_job
from app.services.strategy_parser import OpenAIStrategyParser


def process_preview_job(
    job_id: str,
    user_id: str,
    strategy_text: str,
    strategy_name: str | None,
) -> None:
    """Process one minimal queue payload; PostgreSQL remains the source of truth."""
    del user_id, strategy_text, strategy_name
    with SessionLocal() as session:
        run_preview_job(
            session,
            job_id=UUID(job_id),
            parser=OpenAIStrategyParser.from_settings(),
        )
