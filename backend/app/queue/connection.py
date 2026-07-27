from functools import lru_cache

from redis import Redis
from redis.backoff import ExponentialBackoff
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from redis.retry import Retry as RedisRetry
from rq import Queue

from app.core.config import get_settings
from app.queue.preview_queue import RqPreviewQueue


@lru_cache
def get_redis_connection() -> Redis:
    """Return the process-wide Redis client and bounded connection pool."""
    settings = get_settings()
    retry = RedisRetry(
        ExponentialBackoff(cap=1.0, base=0.1),
        retries=settings.redis_connection_retries,
    )
    connection: Redis = Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
        str(settings.redis_url),
        retry=retry,
        retry_on_error=[RedisConnectionError, RedisTimeoutError],
        socket_connect_timeout=settings.redis_connect_timeout_seconds,
        socket_timeout=settings.redis_socket_timeout_seconds,
        health_check_interval=30,
    )
    return connection


@lru_cache
def get_preview_queue() -> RqPreviewQueue:
    settings = get_settings()
    connection = get_redis_connection()
    return RqPreviewQueue(
        Queue(settings.preview_queue_name, connection=connection),
        job_timeout=settings.preview_job_timeout_seconds,
        max_retries=settings.preview_job_max_retries,
        retry_intervals=settings.preview_job_retry_intervals_seconds,
        result_ttl=settings.preview_job_result_ttl_seconds,
        failure_ttl=settings.preview_job_failure_ttl_seconds,
    )
