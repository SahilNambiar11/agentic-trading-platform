import os

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://postgres:postgres@127.0.0.1:54322/postgres",
)
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
