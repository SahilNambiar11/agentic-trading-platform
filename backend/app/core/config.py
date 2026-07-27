from enum import StrEnum
from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import (
    AnyHttpUrl,
    Field,
    PostgresDsn,
    RedisDsn,
    SecretStr,
    field_validator,
    model_validator,
)
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
    database_connect_timeout_seconds: int = Field(default=5, gt=0, le=30)
    database_pool_size: int = Field(default=5, gt=0, le=50)
    database_max_overflow: int = Field(default=5, ge=0, le=50)
    database_pool_timeout_seconds: int = Field(default=10, gt=0, le=60)
    database_pool_recycle_seconds: int = Field(default=300, gt=0, le=3600)
    redis_url: RedisDsn
    redis_connect_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    redis_socket_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    redis_connection_retries: int = Field(default=2, ge=0, le=10)
    supabase_url: AnyHttpUrl
    supabase_anon_key: SecretStr
    supabase_auth_timeout_seconds: float = 5.0
    cors_origins: list[AnyHttpUrl]
    openai_api_key: SecretStr | None = None
    openai_model: str | None = None
    preview_job_ttl_hours: int = Field(default=24, gt=0, le=168)
    preview_job_timeout_seconds: int = Field(default=180, gt=0, le=3600)
    preview_job_max_retries: int = Field(default=2, ge=0, le=10)
    preview_job_retry_intervals_seconds: list[int] = [5, 30]
    preview_job_result_ttl_seconds: int = Field(default=86400, ge=0)
    preview_job_failure_ttl_seconds: int = Field(default=604800, gt=0)
    preview_job_stale_after_seconds: int = Field(default=300, gt=0, le=86400)
    preview_job_reconciliation_batch_size: int = Field(default=100, gt=0, le=1000)
    preview_job_registry_scan_limit: int = Field(default=1000, gt=0, le=10000)
    preview_job_lock_wait_seconds: float = Field(default=5.0, gt=0, le=30)
    preview_queue_name: str = "preview"

    @field_validator("preview_job_retry_intervals_seconds")
    @classmethod
    def validate_retry_intervals(cls, intervals: list[int]) -> list[int]:
        if any(interval < 0 for interval in intervals):
            raise ValueError("preview job retry intervals must be nonnegative")
        return intervals

    @model_validator(mode="after")
    def validate_retry_configuration(self) -> "Settings":
        if len(self.preview_job_retry_intervals_seconds) < self.preview_job_max_retries:
            raise ValueError("preview job retry intervals must cover every configured retry")
        return self

    @model_validator(mode="after")
    def validate_production_configuration(self) -> "Settings":
        """Reject local endpoints and obvious placeholders in production."""
        if self.environment != Environment.PRODUCTION:
            return self

        database_parts = urlsplit(str(self.database_url))
        database_host = (database_parts.hostname or "").lower()
        supabase_host = (self.supabase_url.host or "").lower()
        local_hosts = {"localhost", "127.0.0.1", "::1", "host.docker.internal"}
        placeholder_markers = (
            "replace_me",
            "replace-with",
            "replace_with",
            "project_ref",
        )
        if (
            database_host in local_hosts
            or database_parts.port == 54322
            or any(marker in database_host for marker in placeholder_markers)
        ):
            raise ValueError("production DATABASE_URL must use hosted PostgreSQL")
        if (
            supabase_host in local_hosts
            or supabase_host.endswith(".localhost")
            or any(marker in supabase_host for marker in placeholder_markers)
        ):
            raise ValueError("production SUPABASE_URL must use hosted Supabase")
        if any(
            origin.host is not None and origin.host.lower().endswith(".example.com")
            for origin in self.cors_origins
        ):
            raise ValueError("production CORS_ORIGINS must use deployed frontend origins")

        required_values = {
            "DATABASE_URL password": database_parts.password,
            "SUPABASE_ANON_KEY": self.supabase_anon_key.get_secret_value(),
            "OPENAI_API_KEY": (
                self.openai_api_key.get_secret_value() if self.openai_api_key is not None else None
            ),
            "OPENAI_MODEL": self.openai_model,
        }
        for name, value in required_values.items():
            normalized = (value or "").strip().lower()
            if not normalized or any(marker in normalized for marker in placeholder_markers):
                raise ValueError(f"production {name} must be configured")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings object.

    The cache avoids reparsing `.env` and revalidating environment values every
    time another module asks for configuration.
    """
    return Settings()  # pyright: ignore[reportCallIssue]
