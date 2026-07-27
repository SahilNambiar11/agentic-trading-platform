import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.core import operations

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Response shape for the public liveness endpoint."""

    status: Literal["ok"]


class ReadinessResponse(BaseModel):
    """Response shape for the dependency readiness endpoint."""

    status: Literal["ready"]


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Return a simple public signal that the API process is running."""
    return HealthResponse(status="ok")


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Dependencies unavailable"}},
)
def ready() -> ReadinessResponse:
    """Report ready only when both PostgreSQL and Redis respond within bounds."""
    dependency_failures: list[str] = []
    for dependency, check in (
        ("postgresql", operations.check_database),
        ("redis", operations.check_redis),
    ):
        try:
            check()
        except Exception:
            dependency_failures.append(dependency)

    if dependency_failures:
        logger.warning(
            "API readiness check failed",
            extra={
                "event": "readiness",
                "component": "api",
                "dependency": ",".join(dependency_failures),
                "outcome": "not_ready",
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service dependencies are unavailable.",
        )
    return ReadinessResponse(status="ready")
