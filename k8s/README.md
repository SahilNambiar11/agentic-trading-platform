# Kubernetes deployment

These manifests use Kubernetes `v1`, `apps/v1`, `networking.k8s.io/v1`, and
`policy/v1` APIs only. They target Kubernetes 1.30+ and run on K3s without
K3s-specific resources.

## Architecture and scaling assumptions

- Frontend: two replicas. The application stores authentication in Supabase
  cookies and contains no server actions or pod-local user session store. Both
  replicas use the same immutable frontend image and build output.
- Backend: two replicas. API startup validates dependencies but does not
  reconcile RQ jobs, so multiple API replicas cannot duplicate recovery work.
- Worker: one replica initially. Multiple workers are supported: RQ scheduler
  locking, PostgreSQL/RQ reconciliation checks, and per-job PostgreSQL advisory
  locks prevent concurrent execution. The `Recreate` strategy avoids overlap
  during the initial single-worker rollout.
- Redis: one replica with AOF persistence (`appendonly yes`,
  `appendfsync everysec`) mounted at `/data`.
- Redis PVC: `ReadWriteOnce`, appropriate for one Redis pod on the first
  single-node K3s target. A future multi-node HA Redis design requires a
  different storage and replication plan.

## Images

The checked-in manifests use explicit example tags, never `latest`:

- `ghcr.io/your-org/agentic-trading-frontend:0.1.0`
- `ghcr.io/your-org/agentic-trading-backend:0.1.0`
- `ghcr.io/your-org/agentic-trading-worker:0.1.0`
- `redis:7.4-alpine`

Build and push the three application images, then substitute your registry and
an immutable release tag or digest before deployment:

```bash
kubectl kustomize k8s > /tmp/agentic-trading.yaml
sed -i.bak 's#ghcr.io/your-org/#ghcr.io/YOUR_ORG/#g' k8s/*.yaml
sed -i.bak 's#:0.1.0#:YOUR_RELEASE_TAG#g' k8s/*.yaml
```

For automated delivery, prefer a Kustomize overlay using the `images` field
instead of editing base manifests. Use the same frontend image for both
frontend replicas and preserve matching asset/build IDs.

The frontend image must be built with:

```text
NEXT_PUBLIC_API_BASE_URL=https://api.example.com
NEXT_PUBLIC_SUPABASE_URL=https://PROJECT_REF.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<matching public key>
```

`NEXT_PUBLIC_API_BASE_URL` must exactly correspond to the public API hostname
configured in `ingress.yaml`. These values are build-time inputs, not runtime
Kubernetes configuration.

## Configuration and secrets

Before deployment:

1. Replace `frontend.example.com` and `api.example.com` in the Ingress.
2. Update `CORS_ORIGINS` in `configmaps.yaml` with the public frontend origin.
3. Create the Secret from a protected local file or secret manager.

`secret.example.yaml` is a non-deployable template containing obvious
placeholders. It is deliberately excluded from `kustomization.yaml` so a later
`kubectl apply -k` cannot overwrite real credentials.

Example secret creation:

```bash
kubectl apply -f k8s/namespace.yaml
kubectl -n agentic-trading create secret generic agentic-trading-secrets \
  --from-literal=DATABASE_URL='HOSTED_SESSION_POOLER_URL' \
  --from-literal=SUPABASE_URL='https://PROJECT_REF.supabase.co' \
  --from-literal=SUPABASE_ANON_KEY='PUBLIC_ANON_KEY' \
  --from-literal=OPENAI_API_KEY='PROVIDER_KEY' \
  --from-literal=OPENAI_MODEL='MODEL_NAME' \
  --dry-run=client -o yaml | kubectl apply -f -
```

Do not store generated Secret YAML in Git. Production application validation
rejects local database/Auth endpoints and obvious placeholder values.

## Deployment order

Apply reviewed Supabase migrations before application rollout. Then:

```bash
kubectl apply -f k8s/namespace.yaml
# Create agentic-trading-secrets as shown above.
kubectl apply -k k8s
kubectl -n agentic-trading rollout status deployment/redis
kubectl -n agentic-trading rollout status deployment/backend
kubectl -n agentic-trading rollout status deployment/worker
kubectl -n agentic-trading rollout status deployment/frontend
```

Kubernetes may create all resources in one apply. Startup probes and
application-level dependency checks provide ordering:

1. Redis becomes ready and restores its AOF from the PVC.
2. Backend validates Redis and hosted PostgreSQL before serving.
3. Worker validates both dependencies, reconciles jobs, starts the RQ scheduler,
   and begins consuming `preview`.
4. Frontend starts independently; readiness is a local TCP check.

## Ingress and TLS

The Ingress omits `ingressClassName`, allowing the cluster's default controller
(including default K3s Traefik) to claim it. It uses separate frontend and API
hostnames and contains no cloud annotations.

TLS is optional until a certificate is provisioned. Once a standard
`kubernetes.io/tls` Secret named `agentic-trading-tls` exists, add:

```yaml
spec:
  tls:
    - hosts:
        - frontend.example.com
        - api.example.com
      secretName: agentic-trading-tls
```

No certificate issuer or cloud-specific TLS integration is assumed.

## Network policies

Ingress is denied by default within the namespace, then allowed to:

- frontend port 3000 from the ingress path;
- backend port 8000 from the ingress path;
- Redis port 6379 only from backend and worker pods.

Frontend/backend ingress rules intentionally do not restrict source namespaces,
because ingress-controller labels and namespaces are not portable across K3s,
EKS, GKE, AKS, and other distributions.

No egress-deny policy is installed. Standard NetworkPolicy cannot portably
allow hosted Supabase and OpenAI by DNS name, and their IP ranges may change.
Leaving egress unrestricted preserves DNS, Supabase, OpenAI, and package/runtime
provider connectivity. Introduce FQDN-aware egress controls only when the chosen
CNI supports them.

## Validation

Render and inspect the complete base:

```bash
kubectl kustomize k8s > /tmp/agentic-trading-rendered.yaml
kubectl apply --dry-run=client --validate=false \
  -f /tmp/agentic-trading-rendered.yaml
kubectl apply --dry-run=client --validate=false \
  -f k8s/secret.example.yaml
```

The Secret reference is an intentional external prerequisite. All other
selectors, ConfigMap references, Services, named ports, and PVC references are
contained in the rendered base.
