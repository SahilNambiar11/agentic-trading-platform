from uuid import UUID

from pydantic import BaseModel


class AuthenticatedUser(BaseModel):
    """Subset of the Supabase user object the backend exposes to route code."""

    id: UUID
    email: str | None = None
    role: str
