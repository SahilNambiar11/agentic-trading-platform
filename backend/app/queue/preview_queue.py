from typing import Protocol
from uuid import UUID

from rq import Queue


class PreviewQueue(Protocol):
    def enqueue(
        self, *, job_id: UUID, user_id: UUID, strategy_text: str, strategy_name: str | None
    ) -> None: ...


class RqPreviewQueue:
    def __init__(self, queue: Queue) -> None:
        self._queue = queue

    def enqueue(
        self, *, job_id: UUID, user_id: UUID, strategy_text: str, strategy_name: str | None
    ) -> None:
        self._queue.enqueue(  # pyright: ignore[reportUnknownMemberType]
            "app.workers.preview_worker.process_preview_job",
            str(job_id),
            str(user_id),
            strategy_text,
            strategy_name,
        )
