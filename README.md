# Agentic Trading Platform

## Local startup

Install the backend and frontend dependencies, then start the repository's
single local Supabase project and generate local configuration:

```bash
./scripts/setup-local-supabase.sh
```

Start Redis, the API, and the worker in containers:

```bash
docker compose up --build
```

In a second terminal, start the frontend:

```bash
cd frontend
npm run dev
```

For a host-run backend instead, start only Redis with `docker compose up redis`,
then run `uvicorn app.main:app --reload` from an activated backend virtual
environment.

The setup script starts local Supabase, reads its status without displaying
credentials, and configures the frontend, backend, and Docker backend to use
that one project. It preserves non-Supabase backend settings already present in
the local backend environment file. Local environment files are ignored by Git.
