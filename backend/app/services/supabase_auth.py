import httpx
from pydantic import ValidationError

from app.schemas.auth import AuthenticatedUser


class InvalidAccessTokenError(Exception):
    """Raised when Supabase rejects a user access token."""


class AuthServiceUnavailableError(Exception):
    """Raised when Supabase Auth cannot reliably verify a token."""


class SupabaseAuthClient:
    def __init__(self, http_client: httpx.AsyncClient, supabase_url: str, api_key: str) -> None:
        self._http_client = http_client
        self._user_url = f"{supabase_url.rstrip('/')}/auth/v1/user"
        self._api_key = api_key

    async def get_user(self, access_token: str) -> AuthenticatedUser:
        try:
            response = await self._http_client.get(
                self._user_url,
                headers={
                    "apikey": self._api_key,
                    "Authorization": f"Bearer {access_token}",
                },
            )
        except httpx.HTTPError as exc:
            raise AuthServiceUnavailableError from exc

        if response.status_code in {401, 403}:
            raise InvalidAccessTokenError

        if not response.is_success:
            raise AuthServiceUnavailableError

        try:
            return AuthenticatedUser.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise AuthServiceUnavailableError from exc
