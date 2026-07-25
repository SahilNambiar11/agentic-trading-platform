from redis import Redis
from rq import Queue

from app.core.config import get_settings
from app.queue.preview_queue import RqPreviewQueue


def get_preview_queue() -> RqPreviewQueue:
    settings = get_settings()
    connection = Redis.from_url(str(settings.redis_url))  # pyright: ignore[reportUnknownMemberType]
    return RqPreviewQueue(Queue(settings.preview_queue_name, connection=connection))
