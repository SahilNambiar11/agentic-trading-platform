from typing import Protocol, cast
from uuid import UUID

from rq import Queue, Retry
from rq.exceptions import NoSuchJobError
from rq.job import Callback
from rq.registry import DeferredJobRegistry, ScheduledJobRegistry, StartedJobRegistry

FAILURE_CALLBACK = "app.workers.preview_worker.handle_preview_job_failure"
FAILURE_CALLBACK_TIMEOUT_SECONDS = 30


class PreviewQueue(Protocol):
    def enqueue(
        self,
        *,
        job_id: UUID,
        user_id: UUID,
        strategy_text: str,
        strategy_name: str | None,
        retry_count: int | None = None,
    ) -> None: ...

    def active_preview_job_ids(self, *, scan_limit: int) -> set[UUID]: ...


class RqPreviewQueue:
    def __init__(
        self,
        queue: Queue,
        *,
        job_timeout: int,
        max_retries: int,
        retry_intervals: list[int],
        result_ttl: int,
        failure_ttl: int,
    ) -> None:
        self._queue = queue
        self._job_timeout = job_timeout
        self._max_retries = max_retries
        self._retry_intervals = retry_intervals
        self._result_ttl = result_ttl
        self._failure_ttl = failure_ttl

    def enqueue(
        self,
        *,
        job_id: UUID,
        user_id: UUID,
        strategy_text: str,
        strategy_name: str | None,
        retry_count: int | None = None,
    ) -> None:
        retries = self._max_retries if retry_count is None else retry_count
        retry = (
            Retry(max=retries, interval=self._retry_intervals[-retries:]) if retries > 0 else None
        )
        self._queue.enqueue_call(  # pyright: ignore[reportUnknownMemberType]
            func="app.workers.preview_worker.process_preview_job",
            args=(str(job_id), str(user_id), strategy_text, strategy_name),
            timeout=self._job_timeout,
            retry=retry,
            result_ttl=self._result_ttl,
            failure_ttl=self._failure_ttl,
            on_failure=Callback(
                FAILURE_CALLBACK,
                timeout=FAILURE_CALLBACK_TIMEOUT_SECONDS,
            ),
        )

    def active_preview_job_ids(self, *, scan_limit: int) -> set[UUID]:
        """Return preview IDs represented by active jobs in this queue only."""
        registries = (
            StartedJobRegistry(queue=self._queue),
            DeferredJobRegistry(queue=self._queue),
            ScheduledJobRegistry(queue=self._queue),
        )
        rq_job_ids = self._queue.get_job_ids(offset=0, length=scan_limit + 1)
        if len(rq_job_ids) > scan_limit:
            raise RuntimeError("Preview queue exceeds the bounded reconciliation scan limit.")

        for registry in registries:
            remaining = scan_limit - len(rq_job_ids)
            if remaining < 0:
                raise RuntimeError("Preview registries exceed the reconciliation scan limit.")
            registry_ids = registry.get_job_ids(
                start=0,
                end=remaining,
                cleanup=False,
            )
            rq_job_ids.extend(registry_ids)
            if len(rq_job_ids) > scan_limit:
                raise RuntimeError("Preview registries exceed the reconciliation scan limit.")

        preview_ids: set[UUID] = set()
        for rq_job_id in set(rq_job_ids):
            try:
                job = self._queue.fetch_job(rq_job_id)
            except NoSuchJobError:
                continue
            if job is None or job.func_name != "app.workers.preview_worker.process_preview_job":
                continue
            raw_args = cast(
                tuple[object, ...],
                job.args,  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
            )
            if not raw_args:
                continue
            try:
                preview_ids.add(UUID(str(raw_args[0])))
            except (TypeError, ValueError):
                continue
        return preview_ids
