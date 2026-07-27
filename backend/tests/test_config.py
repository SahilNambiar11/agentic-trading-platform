import pytest
from pydantic import ValidationError

from app.core.config import Settings


def production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "production",
        "database_url": (
            "postgresql://postgres.project:encoded-password"
            "@aws-0-us-east-1.pooler.supabase.com:5432/postgres"
        ),
        "redis_url": "redis://redis:6379/0",
        "supabase_url": "https://project.supabase.co",
        "supabase_anon_key": "public-anon-value",
        "cors_origins": ["https://trading.acme.test"],
        "openai_api_key": "test-provider-key",
        "openai_model": "test-model",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # pyright: ignore[reportCallIssue]


def test_production_configuration_accepts_hosted_dependencies() -> None:
    settings = production_settings()

    assert settings.environment == "production"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        (
            "database_url",
            "postgresql://postgres:postgres@127.0.0.1:54322/postgres",
        ),
        ("supabase_url", "http://127.0.0.1:54321"),
        ("supabase_anon_key", "REPLACE_ME"),
        ("openai_api_key", "REPLACE_ME"),
        ("openai_model", "REPLACE_ME"),
        ("cors_origins", ["https://frontend.example.com"]),
    ],
)
def test_production_configuration_rejects_local_or_placeholder_values(
    name: str,
    value: object,
) -> None:
    with pytest.raises(ValidationError):
        production_settings(**{name: value})
