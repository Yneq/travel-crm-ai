# Local Kubernetes deployment

This is a single-node, local demonstration of the existing VoyageOps API,
worker, MySQL, and Redis. It runs the deterministic AI providers and needs no
NVIDIA GPU or Gemini API key. The MLX benchmark remains a separate Mac host
process; it is not part of the API container image.

Prerequisites: a running Docker daemon, `kind`, and `kubectl`. From the repo
root, build the application image and load it into a local kind cluster:

```bash
docker build -t travel-crm-ai-api:local .
kind create cluster --name voyageops
kind load docker-image travel-crm-ai-api:local --name voyageops
```

Create local secrets outside Git before applying the workloads. Replace every
placeholder in the copied file; the file is ignored by Git.

```bash
cp k8s/local/secrets.env.example k8s/local/secrets.env
# Edit k8s/local/secrets.env
kubectl apply -f k8s/local/namespace.yaml
kubectl -n voyageops create secret generic voyageops-secrets \
  --from-env-file=k8s/local/secrets.env --dry-run=client -o yaml \
  | kubectl apply -f -
kubectl apply -k k8s/local
```

The API's init container runs the checksum-verified SQL migrations after MySQL
becomes available. The worker retries while its dependencies start. Check the
rollouts and expose the API locally:

```bash
kubectl -n voyageops rollout status statefulset/mysql --timeout=180s
kubectl -n voyageops rollout status deployment/redis --timeout=120s
kubectl -n voyageops rollout status deployment/api --timeout=180s
kubectl -n voyageops rollout status deployment/worker --timeout=120s
kubectl -n voyageops port-forward svc/api 8080:8080
```

In another terminal, check `http://localhost:8080/health/ready`,
`http://localhost:8080/metrics`, and `http://localhost:8080/admin`. If the API
does not become ready, inspect `kubectl -n voyageops describe pod -l app=api`
and `kubectl -n voyageops logs deployment/api -c migrate`.

`kubectl kustomize k8s/local` validates and renders the local manifests without
a cluster. The MySQL StatefulSet uses a 5 Gi persistent volume; Redis is
ephemeral because MySQL stores the durable job ledger. This configuration is a
local deployment demonstration, not a production high-availability setup.
