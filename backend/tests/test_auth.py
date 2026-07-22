import asyncio
from collections.abc import Generator
from contextlib import contextmanager
from uuid import UUID

import httpx
from fastapi.testclient import TestClient

from app.api.dependencies.auth import get_supabase_auth_client
from app.main import app
from app.schemas.auth import AuthenticatedUser
from app.services.supabase_auth import (
    AuthServiceUnavailableError,
    InvalidAccessTokenError,
    SupabaseAuthClient,
)

USER_ID = UUID("6c5c0144-9e69-4c9f-96f0-ed34c28ad02a")


class StubAuthClient:
    """Test double for SupabaseAuthClient.

    Route tests can inject this object to simulate valid users, invalid tokens,
    and unavailable auth service responses without making network calls.
    """

    def __init__(
        self,
        user: AuthenticatedUser | None = None,
        error: Exception | None = None,
    ) -> None:
        self.user = user
        self.error = error

    async def get_user(self, access_token: str) -> AuthenticatedUser:
        if self.error is not None:
            raise self.error
        if self.user is None:
            raise AssertionError("StubAuthClient requires a user or error")
        return self.user


@contextmanager
def client_with_auth(auth_client: StubAuthClient) -> Generator[TestClient]:
    """Create a TestClient with the auth dependency pointed at the stub."""
    app.dependency_overrides[get_supabase_auth_client] = lambda: auth_client
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def test_auth_me_requires_bearer_token() -> None:
    """Protected auth route should reject requests without Authorization."""
    with client_with_auth(StubAuthClient(error=AssertionError("must not verify"))) as client:
        response = client.get("/auth/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"detail": "Invalid or missing authentication credentials."}


def test_auth_me_rejects_invalid_access_token() -> None:
    with client_with_auth(StubAuthClient(error=InvalidAccessTokenError())) as client:
        response = client.get(
            "/auth/me",
            headers={"Authorization": "Bearer invalid-token"},
        )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_auth_me_returns_verified_user() -> None:
    user = AuthenticatedUser(id=USER_ID, email="trader@example.com", role="authenticated")

    with client_with_auth(StubAuthClient(user=user)) as client:
        response = client.get(
            "/auth/me",
            headers={"Authorization": "Bearer valid-token"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "id": str(USER_ID),
        "email": "trader@example.com",
        "role": "authenticated",
    }


def test_auth_me_reports_auth_service_failure() -> None:
    with client_with_auth(StubAuthClient(error=AuthServiceUnavailableError())) as client:
        response = client.get(
            "/auth/me",
            headers={"Authorization": "Bearer valid-token"},
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Authentication service is temporarily unavailable."}


def test_supabase_auth_client_verifies_user_with_auth_server() -> None:
    """The real auth client should call Supabase with apikey and bearer token."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/auth/v1/user"
        assert request.headers["apikey"] == "test-api-key"
        assert request.headers["authorization"] == "Bearer valid-token"
        return httpx.Response(
            200,
            json={
                "id": str(USER_ID),
                "email": "trader@example.com",
                "role": "authenticated",
            },
        )

    async def verify_user() -> AuthenticatedUser:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            auth_client = SupabaseAuthClient(
                http_client=http_client,
                supabase_url="http://supabase.test",
                api_key="test-api-key",
            )
            return await auth_client.get_user("valid-token")

    user = asyncio.run(verify_user())

    assert user.id == USER_ID
    assert user.email == "trader@example.com"


def test_supabase_auth_client_maps_unauthorized_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "invalid JWT"})

    async def verify_user() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            auth_client = SupabaseAuthClient(
                http_client=http_client,
                supabase_url="http://supabase.test",
                api_key="test-api-key",
            )
            await auth_client.get_user("invalid-token")

    try:
        asyncio.run(verify_user())
    except InvalidAccessTokenError:
        pass
    else:
        raise AssertionError("Expected InvalidAccessTokenError")
