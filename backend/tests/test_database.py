from app.db.session import create_database_engine


def test_supabase_database_url_uses_psycopg_driver() -> None:
    engine = create_database_engine("postgresql://postgres:postgres@127.0.0.1:54322/postgres")

    assert engine.url.drivername == "postgresql+psycopg"
    engine.dispose()
