from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def create_database_engine(database_url: str) -> Engine:
    """Create the SQLAlchemy engine used to talk to Postgres.

    Supabase/Postgres URLs commonly use the generic `postgresql://` scheme. This
    function upgrades that to `postgresql+psycopg://` so SQLAlchemy uses the
    psycopg v3 driver declared in `pyproject.toml`.
    """
    url = make_url(database_url)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    return create_engine(url, pool_pre_ping=True)


engine = create_database_engine(str(get_settings().database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db_session() -> Generator[Session]:
    """FastAPI dependency that gives each request its own database session."""
    with SessionLocal() as session:
        yield session
