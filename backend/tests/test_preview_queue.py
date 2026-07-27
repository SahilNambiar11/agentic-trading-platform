from typing import Any, cast
from uuid import uuid4

from pytest import MonkeyPatch
from rq import Queue
from rq.job import Callback

from app.queue import preview_queue
from app.queue.preview_queue import FAILURE_CALLBACK, RqPreviewQueue


class RecordingRqQueue:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def enqueue_call(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


class RegistryQueue:
    def __init__(self, jobs: dict[str, object], queued_ids: list[str]) -> None:
        self.jobs = jobs
        self.queued_ids = queued_ids

    def get_job_ids(self, *, offset: int, length: int) -> list[str]:
        assert offset == 0
        return self.queued_ids[:length]

    def fetch_job(self, job_id: str) -> object | None:
        return self.jobs.get(job_id)


class Registry:
    def __init__(self, ids: list[str]) -> None:
        self.ids = ids

    def get_job_ids(self, *, start: int, end: int, cleanup: bool) -> list[str]:
        assert start == 0
        assert cleanup is False
        return self.ids[: end + 1]


class PreviewRqJob:
    def __init__(
        self,
        preview_job_id: object,
        func_name: str = "app.workers.preview_worker.process_preview_job",
    ) -> None:
        self.args = (preview_job_id,)
        self.func_name = func_name


def test_rq_preview_queue_sets_explicit_operational_limits() -> None:
    recording_queue = RecordingRqQueue()
    queue = RqPreviewQueue(
        cast(Queue, recording_queue),
        job_timeout=180,
        max_retries=2,
        retry_intervals=[5, 30],
        result_ttl=86400,
        failure_ttl=604800,
    )
    preview_job_id = uuid4()
    user_id = uuid4()

    queue.enqueue(
        job_id=preview_job_id,
        user_id=user_id,
        strategy_text="Run a 50/200 crossover.",
        strategy_name=None,
    )

    assert len(recording_queue.calls) == 1
    call = recording_queue.calls[0]
    assert call["func"] == "app.workers.preview_worker.process_preview_job"
    assert call["args"] == (
        str(preview_job_id),
        str(user_id),
        "Run a 50/200 crossover.",
        None,
    )
    assert call["timeout"] == 180
    assert call["retry"].max == 2
    assert call["retry"].intervals == [5, 30]
    assert call["result_ttl"] == 86400
    assert call["failure_ttl"] == 604800
    failure_callback = cast(Callback, call["on_failure"])
    assert failure_callback.name == FAILURE_CALLBACK
    assert failure_callback.timeout == 30


def test_recovered_queue_job_uses_only_remaining_delayed_retry() -> None:
    recording_queue = RecordingRqQueue()
    queue = RqPreviewQueue(
        cast(Queue, recording_queue),
        job_timeout=180,
        max_retries=2,
        retry_intervals=[5, 30],
        result_ttl=86400,
        failure_ttl=604800,
    )

    queue.enqueue(
        job_id=uuid4(),
        user_id=uuid4(),
        strategy_text="Run a 50/200 crossover.",
        strategy_name=None,
        retry_count=1,
    )

    retry = recording_queue.calls[0]["retry"]
    assert retry.max == 1
    assert retry.intervals == [30]


def test_rq_preview_queue_can_disable_retries_explicitly() -> None:
    recording_queue = RecordingRqQueue()
    queue = RqPreviewQueue(
        cast(Queue, recording_queue),
        job_timeout=60,
        max_retries=0,
        retry_intervals=[],
        result_ttl=0,
        failure_ttl=3600,
    )

    queue.enqueue(
        job_id=uuid4(),
        user_id=uuid4(),
        strategy_text="Run a 20/50 crossover.",
        strategy_name=None,
    )

    assert recording_queue.calls[0]["retry"] is None


def test_active_scan_combines_only_preview_queue_and_active_registries(
    monkeypatch: MonkeyPatch,
) -> None:
    queued_id, started_id, deferred_id, scheduled_id = [uuid4() for _ in range(4)]
    jobs = {
        "queued-rq": PreviewRqJob(queued_id),
        "started-rq": PreviewRqJob(started_id),
        "deferred-rq": PreviewRqJob(deferred_id),
        "scheduled-rq": PreviewRqJob(scheduled_id),
        "unrelated-rq": PreviewRqJob(uuid4(), "other.worker"),
    }
    raw_queue = RegistryQueue(jobs, ["queued-rq", "unrelated-rq"])
    registries = iter(
        [
            Registry(["started-rq"]),
            Registry(["deferred-rq"]),
            Registry(["scheduled-rq"]),
        ]
    )
    monkeypatch.setattr(
        preview_queue,
        "StartedJobRegistry",
        lambda queue: next(registries),
    )
    monkeypatch.setattr(
        preview_queue,
        "DeferredJobRegistry",
        lambda queue: next(registries),
    )
    monkeypatch.setattr(
        preview_queue,
        "ScheduledJobRegistry",
        lambda queue: next(registries),
    )
    queue = RqPreviewQueue(
        cast(Queue, raw_queue),
        job_timeout=180,
        max_retries=2,
        retry_intervals=[5, 30],
        result_ttl=86400,
        failure_ttl=604800,
    )

    assert queue.active_preview_job_ids(scan_limit=10) == {
        queued_id,
        started_id,
        deferred_id,
        scheduled_id,
    }
