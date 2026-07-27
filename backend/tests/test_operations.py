import asyncio
from typing import Any, cast

from fastapi import FastAPI
from redis import Redis
from sqlalchemy.engine import Engine

from app.core import operations
from app.core.config import Environment, get_settings
from app.main import create_lifespan


class RecordingPool:
    def __init__(self) -> None:
        self.disconnected = False

    def disconnect(self) -> None:
        self.disconnected = True


class RecordingRedis:
    def __init__(self) -> None:
        self.connection_pool = RecordingPool()


class RecordingEngine:
    def __init__(self) -> None:
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


def test_resource_disposal_closes_both_pools() -> None:
    database_engine = RecordingEngine()
    redis_connection = RecordingRedis()

    operations.dispose_resources(
        cast(Engine, database_engine),
        cast(Redis, redis_connection),
    )

    assert database_engine.disposed is True
    assert redis_connection.connection_pool.disconnected is True


def test_api_lifespan_disposes_resources_on_shutdown(monkeypatch: Any) -> None:
    disposals: list[bool] = []
    monkeypatch.setattr(
        operations,
        "dispose_resources",
        lambda: disposals.append(True),
    )

    async def exercise_lifespan() -> None:
        application = FastAPI()
        async with create_lifespan(get_settings())(application):
            assert application.state.supabase_auth_client is not None

    asyncio.run(exercise_lifespan())

    assert disposals == [True]


def test_api_lifespan_validates_dependencies_outside_test_environment(
    monkeypatch: Any,
) -> None:
    validations: list[bool] = []
    settings = get_settings().model_copy(update={"environment": Environment.LOCAL})
    monkeypatch.setattr(
        operations,
        "validate_dependencies",
        lambda: validations.append(True),
    )
    monkeypatch.setattr(operations, "dispose_resources", lambda: None)

    async def exercise_lifespan() -> None:
        async with create_lifespan(settings)(FastAPI()):
            pass

    asyncio.run(exercise_lifespan())

    assert validations == [True]
