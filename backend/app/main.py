from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.services.supabase_auth import SupabaseAuthClient


def create_lifespan(settings: Settings):
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None]:
        async with httpx.AsyncClient(timeout=settings.supabase_auth_timeout_seconds) as http_client:
            application.state.supabase_auth_client = SupabaseAuthClient(
                http_client=http_client,
                supabase_url=str(settings.supabase_url),
                api_key=settings.supabase_anon_key.get_secret_value(),
            )
            yield

    return lifespan


def create_app() -> FastAPI:
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
