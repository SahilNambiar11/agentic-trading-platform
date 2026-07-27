import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core import operations
from app.core.config import Environment, Settings, get_settings
from app.core.logging import configure_logging
from app.services.supabase_auth import SupabaseAuthClient

logger = logging.getLogger(__name__)


def create_lifespan(settings: Settings):
    """Create startup/shutdown wiring for shared app resources.

    FastAPI runs this lifespan context once for the whole application. The
    Supabase auth client is stored on `application.state` so route dependencies
    can reuse one configured HTTP client instead of rebuilding it per request.
    """

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None]:
        logger.info(
            "API startup validation started",
            extra={
                "event": "startup",
                "component": "api",
                "outcome": "started",
            },
        )
        try:
            if settings.environment != Environment.TEST:
                operations.validate_dependencies()
            async with httpx.AsyncClient(
                timeout=settings.supabase_auth_timeout_seconds
            ) as http_client:
                application.state.supabase_auth_client = SupabaseAuthClient(
                    http_client=http_client,
                    supabase_url=str(settings.supabase_url),
                    api_key=settings.supabase_anon_key.get_secret_value(),
                )
                logger.info(
                    "API startup validation completed",
                    extra={
                        "event": "startup",
                        "component": "api",
                        "outcome": "ready",
                    },
                )
                yield
        except Exception:
            logger.exception(
                "API startup failed",
                extra={
                    "event": "startup",
                    "component": "api",
                    "outcome": "failed",
                },
            )
            raise
        finally:
            operations.dispose_resources()
            logger.info(
                "API shutdown completed",
                extra={
                    "event": "shutdown",
                    "component": "api",
                    "outcome": "success",
                },
            )

    return lifespan


def create_app() -> FastAPI:
    """Build and configure the FastAPI application.

    This is the backend entrypoint used by Uvicorn. It loads environment-backed
    settings, configures JSON logging, allows the frontend origin through CORS,
    and mounts the route modules collected in `app.api.router`.
    """
    settings = get_settings()
    configure_logging(settings.log_level)

    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=create_lifespan(settings),
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin).rstrip("/") for origin in settings.cors_origins],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    application.include_router(api_router)
    return application


app = create_app()
