"""Bounded dependency checks and process resource lifecycle helpers."""

import logging
from time import monotonic

from redis import Redis
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.db.session import engine
from app.queue.connection import get_redis_connection

logger = logging.getLogger(__name__)


def check_database(database_engine: Engine = engine) -> None:
    """Verify PostgreSQL connectivity using the engine's bounded timeouts."""
    started = monotonic()
    try:
        with database_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        logger.exception(
            "PostgreSQL dependency check failed",
            extra={
                "event": "dependency_check",
                "component": "backend",
                "dependency": "postgresql",
                "outcome": "failed",
                "duration_ms": round((monotonic() - started) * 1000, 2),
            },
        )
        raise
    logger.info(
        "PostgreSQL dependency check succeeded",
        extra={
            "event": "dependency_check",
            "component": "backend",
            "dependency": "postgresql",
            "outcome": "ready",
            "duration_ms": round((monotonic() - started) * 1000, 2),
        },
    )


def check_redis(redis_connection: Redis | None = None) -> None:
    """Verify Redis connectivity using the shared pool's bounded timeouts."""
    started = monotonic()
    connection = redis_connection or get_redis_connection()
    try:
        connection.ping()  # pyright: ignore[reportUnknownMemberType]
    except Exception:
        logger.exception(
            "Redis dependency check failed",
            extra={
                "event": "dependency_check",
                "component": "backend",
                "dependency": "redis",
                "outcome": "failed",
                "duration_ms": round((monotonic() - started) * 1000, 2),
            },
        )
        raise
    logger.info(
        "Redis dependency check succeeded",
        extra={
            "event": "dependency_check",
            "component": "backend",
            "dependency": "redis",
            "outcome": "ready",
            "duration_ms": round((monotonic() - started) * 1000, 2),
        },
    )


def validate_dependencies(
    database_engine: Engine = engine,
    redis_connection: Redis | None = None,
) -> None:
    """Fail process startup when either required dependency is unavailable."""
    check_database(database_engine)
    check_redis(redis_connection)


def dispose_resources(
    database_engine: Engine = engine,
    redis_connection: Redis | None = None,
) -> None:
    """Release pooled PostgreSQL and Redis resources during process shutdown."""
    started = monotonic()
    connection = redis_connection or get_redis_connection()
    try:
        connection.connection_pool.disconnect()
        logger.info(
            "Redis pool disconnected",
            extra={
                "event": "resource_disposal",
                "component": "backend",
                "dependency": "redis",
                "outcome": "success",
            },
        )
    except Exception:
        logger.exception(
            "Redis pool disconnect failed",
            extra={
                "event": "resource_disposal",
                "component": "backend",
                "dependency": "redis",
                "outcome": "failed",
            },
        )
    try:
        database_engine.dispose()
        logger.info(
            "PostgreSQL engine disposed",
            extra={
                "event": "resource_disposal",
                "component": "backend",
                "dependency": "postgresql",
                "outcome": "success",
                "duration_ms": round((monotonic() - started) * 1000, 2),
            },
        )
    except Exception:
        logger.exception(
            "PostgreSQL engine disposal failed",
            extra={
                "event": "resource_disposal",
                "component": "backend",
                "dependency": "postgresql",
                "outcome": "failed",
                "duration_ms": round((monotonic() - started) * 1000, 2),
            },
        )
