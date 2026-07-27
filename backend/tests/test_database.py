from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.db import session as session_module
from app.db.session import (
    SessionLocal,
    create_database_engine,
    get_db_session,
    normalize_database_url,
)
from app.services.job_store import release_preview_job_lock, try_acquire_preview_job_lock


def test_supabase_database_url_uses_psycopg_driver() -> None:
    engine = create_database_engine("postgresql://postgres:postgres@127.0.0.1:54322/postgres")

    assert engine.url.drivername == "postgresql+psycopg"
    engine.dispose()


def test_remote_database_url_requires_ssl_and_preserves_query_parameters() -> None:
    url = normalize_database_url(
        "postgresql://postgres:secret@example.supabase.com:5432/postgres"
        "?application_name=worker&sslmode=disable"
    )

    assert url.drivername == "postgresql+psycopg"
    assert url.query["application_name"] == "worker"
    assert url.query["sslmode"] == "require"


def test_local_database_url_does_not_force_ssl() -> None:
    url = normalize_database_url(
        "postgresql://postgres:postgres@127.0.0.1:54322/postgres?application_name=local"
    )

    assert url.query["application_name"] == "local"
    assert "sslmode" not in url.query


def test_database_engine_uses_bounded_pool_configuration() -> None:
    database_engine = create_database_engine(
        "postgresql://postgres:postgres@127.0.0.1:54322/postgres",
        connect_timeout=4,
        pool_size=3,
        max_overflow=2,
        pool_timeout=7,
        pool_recycle=240,
    )

    assert database_engine.pool.size() == 3
    assert database_engine.pool.timeout() == 7
    assert database_engine.pool._max_overflow == 2  # pyright: ignore[reportPrivateUsage]
    assert database_engine.pool._recycle == 240  # pyright: ignore[reportPrivateUsage]
    database_engine.dispose()


def test_request_session_rolls_back_on_exception(monkeypatch: Any) -> None:
    class RecordingSession:
        rolled_back = False

        def rollback(self) -> None:
            self.rolled_back = True

    recording_session = RecordingSession()

    @contextmanager
    def session_factory() -> Generator[Session]:
        yield cast(Session, recording_session)

    monkeypatch.setattr(session_module, "SessionLocal", session_factory)
    dependency = get_db_session()
    assert next(dependency) is recording_session

    with pytest.raises(RuntimeError, match="request failed"):
        dependency.throw(RuntimeError("request failed"))

    assert recording_session.rolled_back is True


def test_preview_job_advisory_lock_prevents_concurrent_execution() -> None:
    job_id = uuid4()
    with SessionLocal() as first_session, SessionLocal() as second_session:
        assert try_acquire_preview_job_lock(first_session, job_id) is True
        assert try_acquire_preview_job_lock(second_session, job_id) is False

        release_preview_job_lock(first_session, job_id)

        assert try_acquire_preview_job_lock(second_session, job_id) is True
        release_preview_job_lock(second_session, job_id)
