# Agentic Trading Platform Project Guide

This guide is meant to help you learn the codebase in the right order. The app
is currently an authenticated strategy-library MVP with database groundwork for
future natural-language parsing and deterministic backtesting.

## Current Architecture

```text
Browser / Next.js UI
  -> Supabase Auth creates and stores the user session
  -> frontend/lib/strategies/api.ts reads the Supabase access token
  -> FastAPI receives Authorization: Bearer <token>
  -> FastAPI verifies the token with Supabase Auth
  -> SQLAlchemy reads/writes user-owned rows in Supabase Postgres
```

The most important security rule is that the frontend never sends a trusted
`user_id`. The backend verifies the bearer token and derives the user ID from
Supabase.

## File Structure

```text
.
├── AGENTS.md
├── README.md
├── PROJECT_GUIDE.md
├── docker-compose.yml
├── scripts/
│   └── setup-local-supabase.sh
├── supabase/
│   ├── config.toml
│   └── migrations/
│       └── 20260720224500_create_mvp_tables.sql
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/
│   │   ├── db/
│   │   ├── api/
│   │   ├── services/
│   │   ├── schemas/
│   │   └── models/
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
└── frontend/
    ├── app/
    ├── lib/
    ├── public/
    ├── package.json
    └── next.config.ts
```

## What Each Area Does

`README.md`: Explains local startup at the repository level.

`AGENTS.md`: Defines product and engineering rules. The big ones are:
deterministic backtests, no arbitrary/model-generated code execution, strict
validation, and server-side auth enforcement.

`scripts/setup-local-supabase.sh`: Starts local Supabase and writes ignored env
files for frontend/backend. This is how `frontend/.env.local`, `backend/.env`,
and `backend/.env.docker` get created.

`docker-compose.yml`: Runs Redis, the FastAPI backend, and an idle RQ worker.
The worker is present for future async backtest jobs.

`supabase/migrations/20260720224500_create_mvp_tables.sql`: Defines the database
schema: profiles, strategies, backtest runs, market data, indexes, triggers, and
row-level security policies.

`backend/app/main.py`: FastAPI entrypoint. Creates the app, configures CORS,
sets up the Supabase auth client, and includes routes.

`backend/app/core/config.py`: Typed environment configuration using Pydantic
Settings.

`backend/app/core/logging.py`: JSON logging setup for backend logs.

`backend/app/db/base.py`: Shared SQLAlchemy base class for ORM models.

`backend/app/db/session.py`: Creates the database engine and per-request DB
sessions.

`backend/app/api/router.py`: Central place that mounts all backend route modules.

`backend/app/api/dependencies/auth.py`: FastAPI auth dependency. It verifies the
bearer token and exposes `CurrentUser` to protected routes.

`backend/app/services/supabase_auth.py`: Calls Supabase Auth `/auth/v1/user` to
verify access tokens.

`backend/app/api/routes/health.py`: Public liveness endpoint.

`backend/app/api/routes/auth.py`: Protected `/auth/me` endpoint.

`backend/app/api/routes/strategies.py`: Current main backend feature. Provides
create, list, get, update, and delete operations for user-owned strategies.

`backend/app/schemas/auth.py`: Pydantic shape for an authenticated user.

`backend/app/schemas/strategy.py`: Pydantic request/response validation for
strategies.

`backend/app/models/strategy.py`: SQLAlchemy ORM mapping for the strategies
table.

`backend/tests/`: Backend behavior tests. These are especially useful for
learning what the API promises and what security rules are expected.

`frontend/app/layout.tsx`: Root layout for every frontend route.

`frontend/app/page.tsx`: Current starter homepage. This is not yet the real
product landing page.

`frontend/app/login/page.tsx`: Browser-side Supabase email/password login.

`frontend/app/signup/page.tsx`: Browser-side Supabase account creation.

`frontend/app/dashboard/page.tsx`: Server-protected dashboard page. Redirects to
login if no Supabase user is available from cookies.

`frontend/app/dashboard/logout-button.tsx`: Browser-side Supabase sign-out.

`frontend/app/dashboard/strategy-workspace.tsx`: Stateful dashboard coordinator
for loading, creating, editing, and deleting strategies.

`frontend/app/dashboard/strategy-create-form.tsx`: Controlled form for entering
a new strategy idea.

`frontend/app/dashboard/strategy-list-item.tsx`: One strategy row with view,
edit, and delete modes.

`frontend/app/dashboard/strategy-validation.ts`: Shared frontend validation for
strategy name/description.

`frontend/lib/api/config.ts`: Resolves the FastAPI base URL.

`frontend/lib/supabase/client.ts`: Browser Supabase client.

`frontend/lib/supabase/server.ts`: Server-rendering Supabase client.

`frontend/lib/supabase/proxy.ts` and `frontend/proxy.ts`: Middleware-style
session refresh so Supabase cookies stay current.

`frontend/lib/strategies/api.ts`: The main frontend-to-backend request layer.
It attaches the Supabase access token to FastAPI requests.

`frontend/lib/strategies/types.ts`: TypeScript types matching backend strategy
responses and request payloads.

## Recommended Reading Order

1. Read `README.md` to understand how the project starts.
2. Read `AGENTS.md` to understand the product rules.
3. Read the Supabase migration to learn the data model.
4. Read `backend/app/main.py` to see how the API boots.
5. Read `backend/app/core/config.py` to learn required environment settings.
6. Read `backend/app/api/router.py` to see how routes are mounted.
7. Read `backend/app/api/dependencies/auth.py` to understand auth boundaries.
8. Read `backend/app/services/supabase_auth.py` to see token verification.
9. Read backend schemas, then models, then strategy routes.
10. Read frontend Supabase clients: `client.ts`, `server.ts`, `proxy.ts`.
11. Read login/signup pages to see how sessions are created.
12. Read dashboard page to see server-side protection.
13. Read `frontend/lib/strategies/api.ts` to see request sending.
14. Read dashboard components from parent to child:
    `strategy-workspace.tsx`, `strategy-create-form.tsx`,
    `strategy-list-item.tsx`, `strategy-validation.ts`.
15. Read backend tests last to confirm expected behavior.

## What Is Not Built Yet

- Google/Auth.js sign-in flow.
- LLM natural-language strategy parser.
- Strict strategy JSON schema for indicators/rules.
- Deterministic backtesting engine.
- Backtest queue/job endpoints.
- Metrics calculations and charts.
- LLM explanation of backtest results.
