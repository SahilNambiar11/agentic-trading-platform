from fastapi import APIRouter

from app.api.dependencies.auth import CurrentUser
from app.schemas.auth import AuthenticatedUser

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=AuthenticatedUser)
async def auth_me(current_user: CurrentUser) -> AuthenticatedUser:
    return current_user
