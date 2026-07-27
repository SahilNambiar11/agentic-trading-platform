from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models.preview_job import PreviewJob
from app.services.job_store import claim_job, create_job
from app.services.preview_reconciliation import (
    RECOVERY_FAILURE_MESSAGE,
    reconcile_preview_jobs,
)


class RecordingRecoveryQueue:
    def __init__(self, active_ids: set[UUID] | None = None) -> None:
        self.active_ids = active_ids or set()
        self.enqueued: list[tuple[UUID, int | None]] = []

    def enqueue(
        self,
        *,
        job_id: UUID,
        user_id: UUID,
        strategy_text: str,
        strategy_name: str | None,
        retry_count: int | None = None,
    ) -> None:
        del user_id, strategy_text, strategy_name
        self.enqueued.append((job_id, retry_count))
        self.active_ids.add(job_id)

    def active_preview_job_ids(self, *, scan_limit: int) -> set[UUID]:
        assert len(self.active_ids) <= scan_limit
        return set(self.active_ids)


@pytest.fixture
def db_session() -> Generator[Session]:
    database_engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with database_engine.connect() as connection:
        connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS public")
        connection.exec_driver_sql(
            """
            CREATE TABLE public.preview_jobs (
                id CHAR(32) PRIMARY KEY,
                user_id CHAR(32) NOT NULL,
                status TEXT NOT NULL,
                stage TEXT NOT NULL,
                progress INTEGER NOT NULL,
                strategy_text TEXT NOT NULL,
                strategy_name TEXT,
                error_message TEXT,
                preview_result JSON,
                attempt_count INTEGER NOT NULL,
                created_at DATETIME NOT NULL,
                started_at DATETIME,
                completed_at DATETIME,
                expires_at DATETIME NOT NULL
            )
            """
        )
        connection.commit()
    with Session(database_engine, expire_on_commit=False) as session:
        yield session
    database_engine.dispose()


def make_job(session: Session) -> PreviewJob:
    return create_job(
        session,
        user_id=uuid4(),
        strategy_text="Buy SPY when SMA 20 crosses above SMA 50.",
        strategy_name=None,
        ttl_hours=24,
    )


def reconcile(
    session: Session,
    queue: RecordingRecoveryQueue,
    *,
    acquire_lock=lambda _session, _job_id: True,
) -> None:
    reconcile_preview_jobs(
        session,
        queue,
        max_retries=2,
        stale_after_seconds=300,
        batch_size=100,
        registry_scan_limit=1000,
        now=datetime.now(UTC),
        acquire_lock=acquire_lock,
        release_lock=lambda _session, _job_id: None,
    )


def test_reconciliation_is_idempotent_and_does_not_duplicate_queued_job(
    db_session: Session,
) -> None:
    job = make_job(db_session)
    queue = RecordingRecoveryQueue()

    reconcile(db_session, queue)
    reconcile(db_session, queue)

    assert queue.enqueued == [(job.id, 2)]
    db_session.refresh(job)
    assert job.status == "queued"


def test_active_queued_and_running_jobs_are_not_reenqueued(db_session: Session) -> None:
    queued_job = make_job(db_session)
    running_job = make_job(db_session)
    assert claim_job(db_session, running_job.id) is not None
    queue = RecordingRecoveryQueue({queued_job.id, running_job.id})

    reconcile(db_session, queue)

    assert queue.enqueued == []


def test_stale_orphaned_running_job_recovers_with_remaining_budget(
    db_session: Session,
) -> None:
    job = make_job(db_session)
    claimed = claim_job(db_session, job.id)
    assert claimed is not None
    claimed.started_at = datetime.now(UTC) - timedelta(minutes=10)
    db_session.commit()
    queue = RecordingRecoveryQueue()

    reconcile(db_session, queue)

    db_session.refresh(job)
    assert job.status == "queued"
    assert job.started_at is None
    assert queue.enqueued == [(job.id, 1)]


def test_exhausted_jobs_fail_with_safe_message(db_session: Session) -> None:
    queued_job = make_job(db_session)
    queued_job.attempt_count = 3
    running_job = make_job(db_session)
    running_job.status = "running"
    running_job.stage = "parsing"
    running_job.started_at = datetime.now(UTC) - timedelta(minutes=10)
    running_job.attempt_count = 3
    db_session.commit()
    queue = RecordingRecoveryQueue()

    reconcile(db_session, queue)

    db_session.refresh(queued_job)
    db_session.refresh(running_job)
    assert queued_job.status == "failed"
    assert running_job.status == "failed"
    assert queued_job.error_message == RECOVERY_FAILURE_MESSAGE
    assert running_job.error_message == RECOVERY_FAILURE_MESSAGE
    assert queue.enqueued == []


def test_completed_and_failed_jobs_remain_unchanged(db_session: Session) -> None:
    completed = make_job(db_session)
    completed.status = "completed"
    completed.stage = "completed"
    completed.progress = 100
    failed = make_job(db_session)
    failed.status = "failed"
    failed.stage = "failed"
    failed.progress = 100
    failed.error_message = "Existing safe error."
    db_session.commit()
    queue = RecordingRecoveryQueue()

    reconcile(db_session, queue)

    db_session.refresh(completed)
    db_session.refresh(failed)
    assert completed.status == "completed"
    assert failed.status == "failed"
    assert failed.error_message == "Existing safe error."
    assert queue.enqueued == []


def test_advisory_lock_prevents_recovery_enqueue(db_session: Session) -> None:
    job = make_job(db_session)
    claimed = claim_job(db_session, job.id)
    assert claimed is not None
    claimed.started_at = datetime.now(UTC) - timedelta(minutes=10)
    db_session.commit()
    queue = RecordingRecoveryQueue()

    reconcile(db_session, queue, acquire_lock=lambda _session, _job_id: False)

    db_session.refresh(job)
    assert job.status == "running"
    assert queue.enqueued == []
