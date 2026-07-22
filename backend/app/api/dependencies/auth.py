from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.schemas.auth import AuthenticatedUser
from app.services.supabase_auth import (
    AuthServiceUnavailableError,
    InvalidAccessTokenError,
    SupabaseAuthClient,
)

bearer_scheme = HTTPBearer(auto_error=False)


def get_supabase_auth_client(request: Request) -> SupabaseAuthClient:
    return cast(SupabaseAuthClient, request.app.state.supabase_auth_client)


def unauthorized_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing authentication credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    auth_client: Annotated[SupabaseAuthClient, Depends(get_supabase_auth_client)],
) -> AuthenticatedUser:
    if credentials is None:
        raise unauthorized_exception()

    try:
        return await auth_client.get_user(credentials.credentials)
    except InvalidAccessTokenError as exc:
        raise unauthorized_exception() from exc
    except AuthServiceUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is temporarily unavailable.",
        ) from exc


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
