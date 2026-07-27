# Frontend

Next.js App Router frontend for Supabase authentication, strategy management,
preview progress, and backtest charts.

## Local development

Copy `.env.example` to `.env.local`, replace all placeholders, then run:

```bash
npm ci
npm run dev
```

Required public variables:

- `NEXT_PUBLIC_SUPABASE_URL`: hosted Supabase project URL.
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`: matching public anonymous key.
- `NEXT_PUBLIC_API_BASE_URL`: browser-accessible FastAPI URL.

All `NEXT_PUBLIC_*` variables are intentionally public and are frozen into
browser JavaScript during `next build`. Changing a Kubernetes ConfigMap or
container environment after the image is built cannot change these client
values. Rebuild the frontend image for each environment or public endpoint.

The API URL must be reachable by the user's browser. A Compose or Kubernetes
service name such as `http://backend:8000` is not valid for browser code.

## Production image

The Dockerfile uses Next.js standalone output:

```bash
docker build \
  --build-arg NEXT_PUBLIC_API_BASE_URL=https://api.example.com \
  --build-arg NEXT_PUBLIC_SUPABASE_URL=https://PROJECT_REF.supabase.co \
  --build-arg NEXT_PUBLIC_SUPABASE_ANON_KEY=PUBLIC_ANON_VALUE \
  --tag agentic-trading-frontend:0.1.0 \
  .
```

The runtime image contains only the standalone server, static assets, and
public files. It runs as UID/GID 10001 and listens on port 3000.
