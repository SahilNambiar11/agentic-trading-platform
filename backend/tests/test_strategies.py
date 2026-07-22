from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Table, create_engine, select, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import DefaultClause

from app.api.dependencies.auth import get_current_user
from app.db.session import get_db_session
from app.main import app
from app.models.strategy import Strategy
from app.schemas.auth import AuthenticatedUser

USER_ONE_ID = UUID("4b53cd47-e66e-47fb-b1a3-589dbf0eab76")
USER_TWO_ID = UUID("6676e143-4796-4338-b42f-47f85e587e5f")


def authenticated_user(user_id: UUID) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=user_id,
        email=f"{user_id}@example.com",
        role="authenticated",
    )


def authenticate_as(user_id: UUID) -> None:
    app.dependency_overrides[get_current_user] = lambda: authenticated_user(user_id)


@pytest.fixture
def db_session() -> Generator[Session]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    with engine.connect() as connection:
        connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS public")
        connection.exec_driver_sql(
            """
            CREATE TABLE public.strategies (
                id CHAR(32) PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
                user_id CHAR(32) NOT NULL,
                name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
                source_text TEXT NOT NULL CHECK (length(source_text) > 0),
                strategy_json JSON,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (id, user_id)
            )
            """
        )
        connection.exec_driver_sql(
            "CREATE INDEX public.strategies_user_id_idx ON strategies (user_id)"
        )
        connection.commit()

    with Session(engine, expire_on_commit=False) as session:
        yield session

    engine.dispose()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient]:
    def override_db_session() -> Generator[Session]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_db_session
    authenticate_as(USER_ONE_ID)
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_current_user, None)


def create_strategy(
    client: TestClient,
    *,
    name: str = "SMA Crossover",
    source_text: str = "Buy when the short SMA crosses above the long SMA.",
    strategy_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = client.post(
        "/strategies",
        json={
            "name": name,
            "source_text": source_text,
            "strategy_json": strategy_json,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_strategy_model_matches_migration_metadata() -> None:
    table = cast(Table, Strategy.__table__)

    assert table.schema == "public"
    assert list(table.columns.keys()) == [
        "id",
        "user_id",
        "name",
        "source_text",
        "strategy_json",
        "created_at",
        "updated_at",
    ]
    id_default = cast(DefaultClause, table.c.id.server_default)
    user_id_default = cast(DefaultClause, table.c.user_id.server_default)
    assert str(id_default.arg) == "gen_random_uuid()"
    assert str(user_id_default.arg) == "auth.uid()"
    assert isinstance(table.c.strategy_json.type.dialect_impl(postgresql.dialect()), JSONB)
    assert table.c.strategy_json.nullable is True
    assert table.c.created_at.nullable is False
    assert table.c.updated_at.nullable is False

    foreign_key = next(iter(table.c.user_id.foreign_keys))
    assert foreign_key.target_fullname == "auth.users.id"
    assert foreign_key.ondelete == "CASCADE"
    assert {constraint.name for constraint in table.constraints} >= {
        "strategies_name_length_check",
        "strategies_source_text_length_check",
        "strategies_id_user_id_key",
    }
    assert {index.name for index in table.indexes} == {"strategies_user_id_idx"}


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/strategies", {"name": "Test", "source_text": "Buy SPY."}),
        ("GET", "/strategies", None),
        ("GET", f"/strategies/{uuid4()}", None),
        ("PATCH", f"/strategies/{uuid4()}", {"name": "Updated"}),
        ("DELETE", f"/strategies/{uuid4()}", None),
    ],
)
def test_strategy_routes_require_authentication(
    client: TestClient,
    method: str,
    path: str,
    body: dict[str, Any] | None,
) -> None:
    app.dependency_overrides.pop(get_current_user, None)

    response = client.request(method, path, json=body)

    assert response.status_code == 401


def test_authenticated_user_can_create_strategy(
    client: TestClient,
    db_session: Session,
) -> None:
    strategy_json = {"entry": {"indicator": "sma", "period": 20}}

    result = create_strategy(client, strategy_json=strategy_json)

    assert "user_id" not in result
    assert result["name"] == "SMA Crossover"
    assert result["strategy_json"] == strategy_json
    strategy = db_session.scalar(select(Strategy).where(Strategy.id == UUID(result["id"])))
    assert strategy is not None
    assert strategy.user_id == USER_ONE_ID


def test_create_rejects_server_managed_fields(client: TestClient) -> None:
    response = client.post(
        "/strategies",
        json={
            "id": str(uuid4()),
            "user_id": str(USER_TWO_ID),
            "owner_id": str(USER_TWO_ID),
            "name": "Injected owner",
            "source_text": "Buy SPY.",
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        },
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "   ", "source_text": "Buy SPY."},
        {"name": "x" * 201, "source_text": "Buy SPY."},
        {"name": "Valid", "source_text": "   "},
        {"name": "Valid", "source_text": "Buy SPY.", "strategy_json": ["not", "object"]},
    ],
)
def test_create_rejects_invalid_input(client: TestClient, payload: dict[str, Any]) -> None:
    response = client.post("/strategies", json=payload)

    assert response.status_code == 422


def test_list_returns_only_current_users_strategies_in_stable_order(
    client: TestClient,
    db_session: Session,
) -> None:
    older = create_strategy(client, name="Older")
    newer = create_strategy(client, name="Newer")

    db_session.execute(
        update(Strategy)
        .where(Strategy.id == UUID(older["id"]))
        .values(created_at=datetime(2026, 1, 1, tzinfo=UTC))
    )
    db_session.execute(
        update(Strategy)
        .where(Strategy.id == UUID(newer["id"]))
        .values(created_at=datetime(2026, 1, 2, tzinfo=UTC))
    )
    db_session.commit()

    authenticate_as(USER_TWO_ID)
    create_strategy(client, name="Another user's strategy")
    authenticate_as(USER_ONE_ID)

    response = client.get("/strategies")

    assert response.status_code == 200
    assert [strategy["name"] for strategy in response.json()] == ["Newer", "Older"]


def test_owner_can_retrieve_strategy(client: TestClient) -> None:
    strategy = create_strategy(client)

    response = client.get(f"/strategies/{strategy['id']}")

    assert response.status_code == 200
    assert response.json() == strategy


def test_get_returns_not_found_for_missing_strategy(client: TestClient) -> None:
    response = client.get(f"/strategies/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Strategy not found."}


def test_get_returns_not_found_for_another_users_strategy(client: TestClient) -> None:
    strategy = create_strategy(client)
    authenticate_as(USER_TWO_ID)

    response = client.get(f"/strategies/{strategy['id']}")

    assert response.status_code == 404


def test_owner_can_partially_update_strategy(client: TestClient) -> None:
    strategy = create_strategy(
        client,
        source_text="Original source text.",
        strategy_json={"period": 20},
    )

    response = client.patch(
        f"/strategies/{strategy['id']}",
        json={"name": "Updated name"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Updated name"
    assert response.json()["source_text"] == "Original source text."
    assert response.json()["strategy_json"] == {"period": 20}


def test_update_can_clear_strategy_json(client: TestClient) -> None:
    strategy = create_strategy(client, strategy_json={"period": 20})

    response = client.patch(
        f"/strategies/{strategy['id']}",
        json={"strategy_json": None},
    )

    assert response.status_code == 200
    assert response.json()["strategy_json"] is None


def test_update_rejects_server_managed_fields(client: TestClient) -> None:
    strategy = create_strategy(client)

    response = client.patch(
        f"/strategies/{strategy['id']}",
        json={
            "user_id": str(USER_TWO_ID),
            "owner_id": str(USER_TWO_ID),
            "id": str(uuid4()),
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        },
    )

    assert response.status_code == 422


def test_update_rejects_null_required_fields(client: TestClient) -> None:
    strategy = create_strategy(client)

    response = client.patch(
        f"/strategies/{strategy['id']}",
        json={"name": None},
    )

    assert response.status_code == 422


def test_update_returns_not_found_for_another_user(client: TestClient) -> None:
    strategy = create_strategy(client)
    authenticate_as(USER_TWO_ID)

    response = client.patch(
        f"/strategies/{strategy['id']}",
        json={"name": "Not allowed"},
    )

    assert response.status_code == 404


def test_update_returns_not_found_for_missing_strategy(client: TestClient) -> None:
    response = client.patch(
        f"/strategies/{uuid4()}",
        json={"name": "Missing"},
    )

    assert response.status_code == 404


def test_owner_can_delete_strategy(client: TestClient) -> None:
    strategy = create_strategy(client)

    response = client.delete(f"/strategies/{strategy['id']}")
    get_response = client.get(f"/strategies/{strategy['id']}")

    assert response.status_code == 204
    assert response.content == b""
    assert get_response.status_code == 404


def test_delete_returns_not_found_for_another_user(client: TestClient) -> None:
    strategy = create_strategy(client)
    authenticate_as(USER_TWO_ID)

    response = client.delete(f"/strategies/{strategy['id']}")

    assert response.status_code == 404
    authenticate_as(USER_ONE_ID)
    assert client.get(f"/strategies/{strategy['id']}").status_code == 200


def test_delete_returns_not_found_for_missing_strategy(client: TestClient) -> None:
    response = client.delete(f"/strategies/{uuid4()}")

    assert response.status_code == 404
