from enum import StrEnum
from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, PostgresDsn, RedisDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Known deployment environments for configuration-sensitive behavior."""

    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Typed application configuration loaded from env vars and backend/.env.

    Pydantic Settings validates these values at startup. That means a missing
    database URL, Redis URL, Supabase URL/key, or malformed CORS origin fails
    early instead of failing later inside a request handler.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Agentic Trading Platform API"
    environment: Environment = Environment.LOCAL
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    database_url: PostgresDsn
    redis_url: RedisDsn
    supabase_url: AnyHttpUrl
    supabase_anon_key: SecretStr
    supabase_auth_timeout_seconds: float = 5.0
    cors_origins: list[AnyHttpUrl]


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings object.

    The cache avoids reparsing `.env` and revalidating environment values every
    time another module asks for configuration.
    """
    return Settings()  # pyright: ignore[reportCallIssue]
