from collections.abc import Generator
from contextlib import contextmanager
from types import TracebackType
from typing import Any, cast
from uuid import uuid4

from redis import Redis
from rq.job import Job
from sqlalchemy.orm import Session

from app.workers import preview_worker


class CallbackJob:
    def __init__(self, preview_job_id: str, retries_left: int) -> None:
        self.args = (preview_job_id,)
        self.id = "rq-job"
        self.retries_left = retries_left


@contextmanager
def fake_session_factory() -> Generator[Session]:
    yield cast(Session, object())


def test_failure_callback_returns_postgres_job_to_queue_before_retry(
    monkeypatch: Any,
) -> None:
    preview_job_id = uuid4()
    transitions: list[tuple[object, bool]] = []

    def record_transition(
        session: Session,
        *,
        job_id: object,
        will_retry: bool,
    ) -> bool:
        del session
        transitions.append((job_id, will_retry))
        return True

    monkeypatch.setattr(preview_worker, "SessionLocal", fake_session_factory)
    monkeypatch.setattr(
        preview_worker,
        "transition_job_after_operational_failure",
        record_transition,
    )

    preview_worker.handle_preview_job_failure(
        cast(Job, CallbackJob(str(preview_job_id), retries_left=2)),
        cast(Redis, object()),
        TimeoutError,
        TimeoutError(),
        cast(TracebackType | None, None),
    )

    assert transitions == [(preview_job_id, True)]


def test_failure_callback_marks_postgres_job_failed_after_final_attempt(
    monkeypatch: Any,
) -> None:
    preview_job_id = uuid4()
    transitions: list[tuple[object, bool]] = []

    def record_transition(
        session: Session,
        *,
        job_id: object,
        will_retry: bool,
    ) -> bool:
        del session
        transitions.append((job_id, will_retry))
        return True

    monkeypatch.setattr(preview_worker, "SessionLocal", fake_session_factory)
    monkeypatch.setattr(
        preview_worker,
        "transition_job_after_operational_failure",
        record_transition,
    )

    preview_worker.handle_preview_job_failure(
        cast(Job, CallbackJob(str(preview_job_id), retries_left=0)),
        cast(Redis, object()),
        TimeoutError,
        TimeoutError(),
        cast(TracebackType | None, None),
    )

    assert transitions == [(preview_job_id, False)]
