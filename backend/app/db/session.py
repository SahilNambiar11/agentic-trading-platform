from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

LOCAL_DATABASE_HOSTS = {
    "localhost",
    "127.0.0.1",
    "::1",
    "host.docker.internal",
}


def normalize_database_url(database_url: str) -> URL:
    """Select psycopg and require TLS for every non-local PostgreSQL target."""
    url = make_url(database_url)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")

    host = (url.host or "").lower()
    is_local_supabase = url.port == 54322
    if host not in LOCAL_DATABASE_HOSTS and not is_local_supabase:
        url = url.update_query_dict({"sslmode": "require"})
    return url


def create_database_engine(
    database_url: str,
    *,
    connect_timeout: int = 5,
    pool_size: int = 5,
    max_overflow: int = 5,
    pool_timeout: int = 10,
    pool_recycle: int = 300,
) -> Engine:
    """Create the SQLAlchemy engine used to talk to Postgres.

    Supabase/Postgres URLs commonly use the generic `postgresql://` scheme. This
    function upgrades that to `postgresql+psycopg://` so SQLAlchemy uses the
    psycopg v3 driver declared in `pyproject.toml`.
    """
    url = normalize_database_url(database_url)
    return create_engine(
        url,
        connect_args={"connect_timeout": connect_timeout},
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_recycle=pool_recycle,
        pool_use_lifo=True,
    )


settings = get_settings()
engine = create_database_engine(
    str(settings.database_url),
    connect_timeout=settings.database_connect_timeout_seconds,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_timeout=settings.database_pool_timeout_seconds,
    pool_recycle=settings.database_pool_recycle_seconds,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db_session() -> Generator[Session]:
    """FastAPI dependency that gives each request its own database session."""
    with SessionLocal() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
