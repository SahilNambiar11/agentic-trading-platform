from enum import StrEnum
from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, PostgresDsn, RedisDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
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
    return Settings()  # pyright: ignore[reportCallIssue]
