from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared SQLAlchemy base class for ORM models.

    Any model that subclasses this contributes table metadata to `Base.metadata`.
    Tests use that metadata to compare ORM definitions against the Supabase SQL
    migration, and SQLAlchemy uses it to understand relationships/foreign keys.
    """

    pass
