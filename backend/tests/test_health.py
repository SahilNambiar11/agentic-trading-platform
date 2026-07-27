from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.core import operations
from app.main import app


def test_health_stays_dependency_free(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        operations,
        "check_database",
        lambda: (_ for _ in ()).throw(RuntimeError("must not be called")),
    )
    monkeypatch.setattr(
        operations,
        "check_redis",
        lambda: (_ for _ in ()).throw(RuntimeError("must not be called")),
    )
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_when_postgresql_and_redis_are_healthy(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(operations, "check_database", lambda: None)
    monkeypatch.setattr(operations, "check_redis", lambda: None)

    response = TestClient(app).get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_reports_postgresql_failure_without_details(
    monkeypatch: MonkeyPatch,
) -> None:
    def database_failure() -> None:
        raise RuntimeError("sensitive database detail")

    monkeypatch.setattr(operations, "check_database", database_failure)
    monkeypatch.setattr(operations, "check_redis", lambda: None)

    response = TestClient(app).get("/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "Service dependencies are unavailable."}
    assert "sensitive" not in response.text


def test_ready_reports_redis_failure_without_details(monkeypatch: MonkeyPatch) -> None:
    def redis_failure() -> None:
        raise RuntimeError("sensitive redis detail")

    monkeypatch.setattr(operations, "check_database", lambda: None)
    monkeypatch.setattr(operations, "check_redis", redis_failure)

    response = TestClient(app).get("/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "Service dependencies are unavailable."}


def test_ready_reports_dependency_timeout(monkeypatch: MonkeyPatch) -> None:
    def timeout() -> None:
        raise TimeoutError("provider timeout detail")

    monkeypatch.setattr(operations, "check_database", timeout)
    monkeypatch.setattr(operations, "check_redis", lambda: None)

    response = TestClient(app).get("/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "Service dependencies are unavailable."}
