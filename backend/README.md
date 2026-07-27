# Backend

FastAPI backend foundation for the Agentic Trading Platform.

## Prerequisites

- Python 3.12
- Docker with Docker Compose
- A hosted Supabase project

## Local setup

Copy `.env.example` to the ignored `.env` file. Configure the hosted Supabase
session-pooler `DATABASE_URL`, hosted `SUPABASE_URL`, matching anonymous key,
OpenAI provider settings, and local Redis URL.

Then, from `backend/`:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Start the API directly from `backend/`:

```bash
uvicorn app.main:app --reload
```

The API is available at <http://localhost:8000>, interactive documentation at
<http://localhost:8000/docs>, and the liveness endpoint at
<http://localhost:8000/health>.

For host development, run Redis, then separate API and worker processes:

```bash
docker compose up redis
uv run uvicorn app.main:app --reload
uv run python -m app.workers.run_preview_worker --simple-worker
```

Expired preview results can be removed with:

```bash
uv run python -m app.scripts.cleanup_preview_jobs
```

## Configuration

Configuration is loaded from environment variables. For local development,
Pydantic Settings also reads `backend/.env`. See `.env.example` for all required
values. The example contains local-only credentials used by Supabase CLI.

`SUPABASE_URL` must be the base API URL reported by `supabase status`, without a
service path such as `/auth/v1` or `/rest/v1`. Set `SUPABASE_ANON_KEY` to the
matching local anonymous key. `CORS_ORIGINS` is a JSON array of frontend origins
allowed to call the API.

For hosted environments, provide `DATABASE_URL` through the deployment secret
manager using the Supabase session-pooler connection string on port 5432.
Remote PostgreSQL connections automatically require TLS. Never commit hosted
database credentials, service-role keys, provider keys, or access tokens.

Production startup rejects local PostgreSQL/Supabase endpoints and obvious
placeholder credentials. The API validates PostgreSQL and Redis before serving.
`GET /health` is dependency-free liveness; `GET /ready` returns 200 only when
both dependencies are reachable.

The API and worker use the two final targets in the shared `Dockerfile`:

```bash
docker build --target api -t agentic-trading-backend:local .
docker build --target worker -t agentic-trading-worker:local .
```

The production worker entrypoint validates dependencies, performs bounded
idempotent reconciliation, and starts RQ with scheduled retries:

```bash
python -m app.workers.run_preview_worker
```

## Authentication

Protected endpoints expect the Supabase user access token as a bearer token:

```http
Authorization: Bearer <access-token>
```

The backend verifies the token with the configured Supabase Auth server and
derives the user ID from the verified response. It never trusts a `user_id`
provided by a browser request.

Use `GET /auth/me` to verify the integration. It returns the authenticated
user's ID, email, and role. Missing or invalid credentials return `401`; an
unreachable Supabase Auth service returns `503`. The `/health` endpoint remains
public.

Browser code should obtain the current access token from the existing Supabase
session and attach it to FastAPI requests. FastAPI does not consume the Next.js
session cookies directly.

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
