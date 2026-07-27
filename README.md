# Agentic Trading Platform

The application converts constrained natural-language trading strategies into
deterministic backtests. Supabase PostgreSQL and Supabase Auth are hosted
dependencies; production containers run only the Next.js frontend, FastAPI API,
RQ preview worker, and Redis.

## Runtime architecture

```text
Browser ──HTTPS──> Next.js
   │
   ├──HTTPS + Supabase access token──> FastAPI ──TLS──> Hosted Supabase
   │                                      │
   │                                      └──> Redis preview queue
   │                                                │
   └──HTTPS──> Hosted Supabase Auth                 v
                                             RQ preview worker
                                                    │
                                                    └──TLS──> Hosted Supabase
```

## Local development

Create ignored local environment files from the examples. Use hosted Supabase
values in both applications and the same hosted project for frontend Auth,
backend Auth, and PostgreSQL.

Start Redis only:

```bash
docker compose up -d redis
```

Then run the processes in separate terminals:

```bash
cd backend
uv run uvicorn app.main:app --reload
```

```bash
cd backend
uv run python -m app.workers.run_preview_worker --simple-worker
```

```bash
cd frontend
npm run dev
```

## Production Docker Compose

Prepare ignored configuration files:

```bash
cp backend/.env.example backend/.env.production
cp frontend/.env.example frontend/.env.production
```

Replace every placeholder. `backend/.env.production` contains runtime secrets
and server configuration. The three `NEXT_PUBLIC_*` values in
`frontend/.env.production` are public build-time inputs that are frozen into
the frontend image by `next build`.

The browser-facing API value must be a URL the browser can reach. For local
Compose validation use `http://localhost:8000`; never use `http://backend:8000`
as `NEXT_PUBLIC_API_BASE_URL`.

Start or rebuild the complete stack:

```bash
BACKEND_ENV_FILE=./backend/.env.production docker compose --env-file frontend/.env.production up --build -d
```

Perform a clean image rebuild without deleting Redis data:

```bash
BACKEND_ENV_FILE=./backend/.env.production docker compose --env-file frontend/.env.production down --remove-orphans && BACKEND_ENV_FILE=./backend/.env.production docker compose --env-file frontend/.env.production build --pull --no-cache && BACKEND_ENV_FILE=./backend/.env.production docker compose --env-file frontend/.env.production up -d --force-recreate
```

Inspect and stop the stack:

```bash
docker compose ps
BACKEND_ENV_FILE=./backend/.env.production docker compose --env-file frontend/.env.production down
```

`down` preserves the named Redis volume. Add `--volumes` only when intentionally
deleting queued and persisted Redis state.

Images produced by Compose:

- `agentic-trading-frontend:${IMAGE_TAG:-local}` from `frontend/Dockerfile`
- `agentic-trading-backend:${IMAGE_TAG:-local}` from backend target `api`
- `agentic-trading-worker:${IMAGE_TAG:-local}` from backend target `worker`

The worker runs:

```text
python -m app.workers.run_preview_worker
```

## Kubernetes

Portable Kubernetes v1.30+ resources are under [`k8s/`](k8s/README.md). They use
only standard Kubernetes APIs and are compatible with K3s and managed
Kubernetes services. Supabase is never deployed into the cluster.

Do not run schema migrations from application container startup. Review and
apply Supabase CLI migrations separately before rolling out an application
version.
