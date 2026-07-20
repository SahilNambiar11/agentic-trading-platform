# Backend

FastAPI backend foundation for the Agentic Trading Platform.

## Prerequisites

- Python 3.12
- Docker with Docker Compose
- Supabase CLI

## Local setup

From `backend/`:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
cp .env.example .env
```

Initialize Supabase once from the repository root if `supabase/config.toml` does
not exist, then start the local Supabase stack:

```bash
supabase init
supabase start
```

The example `DATABASE_URL` connects directly from the host to Supabase Postgres
on `127.0.0.1:54322`. Use the database URL reported by `supabase status` if the
local ports have been customized.

Start the API directly from `backend/`:

```bash
uvicorn app.main:app --reload
```

The API is available at <http://localhost:8000>, interactive documentation at
<http://localhost:8000/docs>, and the liveness endpoint at
<http://localhost:8000/health>.

To run Redis, the API, and an idle RQ worker in containers from the repository
root:

```bash
docker compose up --build
```

Containers use `host.docker.internal` to reach Supabase Postgres on the host.
The worker listens to the `default` queue and remains idle until jobs are added
in a future implementation.

## Configuration

Configuration is loaded from environment variables. For local development,
Pydantic Settings also reads `backend/.env`. See `.env.example` for all required
values. The example contains local-only credentials used by Supabase CLI.

For hosted environments, provide `DATABASE_URL` through the deployment secret
manager using the Supabase direct or session-pooler connection string. Never
commit hosted database credentials, service-role keys, or access tokens.

## Quality checks

From `backend/` with the development dependencies installed:

```bash
ruff format --check .
ruff check .
pyright
pytest
```

Supabase CLI SQL migrations are the only schema migration system. Create and
test migrations locally from the repository root:

```bash
supabase migration new describe_the_schema_change
supabase db reset
```

Use `supabase db push` only when intentionally applying reviewed migrations to
the linked hosted project. SQLAlchemy remains the Python query and ORM layer; it
does not manage schema migrations.
