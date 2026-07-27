from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, cast

from redis import Redis
from sqlalchemy.orm import Session

from app.services.preview_reconciliation import ReconciliationSummary
from app.workers import run_preview_worker


class RecordingWorker:
    work_calls: list[dict[str, object]] = []

    def __init__(self, queues: object, **kwargs: object) -> None:
        del queues, kwargs

    def work(self, **kwargs: object) -> bool:
        self.work_calls.append(kwargs)
        return True


@contextmanager
def fake_session_factory() -> Generator[Session]:
    yield cast(Session, object())


def test_worker_entrypoint_validates_reconciles_and_enables_scheduler(
    monkeypatch: Any,
) -> None:
    events: list[str] = []
    redis_connection = cast(Redis, object())
    RecordingWorker.work_calls.clear()
    monkeypatch.setattr(run_preview_worker, "get_redis_connection", lambda: redis_connection)
    monkeypatch.setattr(run_preview_worker, "get_preview_queue", lambda: object())
    monkeypatch.setattr(run_preview_worker, "Queue", lambda *args, **kwargs: object())
    monkeypatch.setattr(run_preview_worker, "SimpleWorker", RecordingWorker)
    monkeypatch.setattr(run_preview_worker, "SessionLocal", fake_session_factory)
    monkeypatch.setattr(
        run_preview_worker.operations,
        "validate_dependencies",
        lambda **kwargs: events.append("validated"),
    )
    monkeypatch.setattr(
        run_preview_worker,
        "reconcile_preview_jobs",
        lambda *args, **kwargs: events.append("reconciled") or ReconciliationSummary(scanned=1),
    )
    monkeypatch.setattr(
        run_preview_worker.operations,
        "dispose_resources",
        lambda **kwargs: events.append("disposed"),
    )

    exit_code = run_preview_worker.run(simple_worker=True)

    assert exit_code == 0
    assert events == ["validated", "reconciled", "disposed"]
    assert RecordingWorker.work_calls == [
        {
            "with_scheduler": True,
            "logging_level": run_preview_worker.get_settings().log_level,
        }
    ]


def test_worker_entrypoint_exits_nonzero_and_disposes_after_startup_failure(
    monkeypatch: Any,
) -> None:
    disposed: list[bool] = []
    redis_connection = cast(Redis, object())
    monkeypatch.setattr(run_preview_worker, "get_redis_connection", lambda: redis_connection)
    monkeypatch.setattr(run_preview_worker, "get_preview_queue", lambda: object())

    def fail_validation(**kwargs: object) -> None:
        del kwargs
        raise RuntimeError("dependency unavailable")

    monkeypatch.setattr(
        run_preview_worker.operations,
        "validate_dependencies",
        fail_validation,
    )
    monkeypatch.setattr(
        run_preview_worker.operations,
        "dispose_resources",
        lambda **kwargs: disposed.append(True),
    )

    assert run_preview_worker.run() == 1
    assert disposed == [True]
