# Deployment Guide

## Option A — single node (default, zero infra)

```bash
docker compose -f infra/compose/docker-compose.yml up api web
```

SQLite + local volume + in-process bus/queue. Suitable for evaluation and
small teams. Set `DATAFORGE_SECRET_KEY` and (optionally) `ANTHROPIC_API_KEY`.

## Option B — full stack

```bash
docker compose -f infra/compose/docker-compose.yml --profile full up
```

Adds Postgres, Redis, NATS JetStream, MinIO, Qdrant, Neo4j and a Celery
worker. Point the api service at Postgres/MinIO via environment.

## Option C — Kubernetes

```bash
helm install dataforge infra/helm \
  --set secrets.secretKey=$(openssl rand -hex 32) \
  --set env.DATAFORGE_DATABASE_URL=postgresql+psycopg://…
```

The chart ships API deployment/service with readiness+liveness probes and HPA
values; add managed Postgres/Redis/S3 for production.

## Option D — managed cloud storage (AWS / GCP / Azure)

Raw artifacts and exports live behind the object-store abstraction; agent
scratch state and document metadata can additionally use the NoSQL store.
Both are selected purely by env vars — no code changes.

**Object store** (`DATAFORGE_STORAGE_BACKEND`):

| Backend | Value | Extra deps | Key env vars |
|---|---|---|---|
| Local FS (default) | `local` | — | `DATAFORGE_STORAGE_ROOT` |
| AWS S3 / MinIO | `s3` | `boto3` | `DATAFORGE_S3_BUCKET`, `DATAFORGE_S3_REGION`, `DATAFORGE_S3_ENDPOINT` (MinIO), `DATAFORGE_S3_ACCESS_KEY`, `DATAFORGE_S3_SECRET_KEY` |
| Google Cloud Storage | `gcs` | `google-cloud-storage` | `DATAFORGE_GCS_BUCKET`, `DATAFORGE_GCS_PROJECT`, `DATAFORGE_GCS_CREDENTIALS_FILE` (or ADC) |
| Azure Blob Storage | `azure` | `azure-storage-blob` (+ `azure-identity` for keyless) | `DATAFORGE_AZURE_CONTAINER`, `DATAFORGE_AZURE_CONNECTION_STRING` *or* `DATAFORGE_AZURE_ACCOUNT_URL` [+ `DATAFORGE_AZURE_ACCOUNT_KEY`] |

**NoSQL store** (`DATAFORGE_NOSQL_BACKEND`):

| Backend | Value | Extra deps | Key env vars |
|---|---|---|---|
| SQLite file (default) | `local` | — | `DATAFORGE_STORAGE_ROOT` |
| AWS DynamoDB | `dynamodb` | `boto3` | `DATAFORGE_DYNAMODB_TABLE` (pk=`pk` S, sk=`sk` S), `DATAFORGE_DYNAMODB_REGION`, `DATAFORGE_DYNAMODB_ENDPOINT` (DynamoDB Local) |
| MongoDB / DocumentDB | `mongodb` | `pymongo` | `DATAFORGE_MONGODB_URL`, `DATAFORGE_MONGODB_DATABASE` |
| GCP Firestore | `firestore` | `google-cloud-firestore` | `DATAFORGE_FIRESTORE_PROJECT`, `DATAFORGE_FIRESTORE_CREDENTIALS_FILE` (or ADC) |
| Azure Cosmos DB | `cosmos` | `azure-cosmos` | `DATAFORGE_COSMOS_ENDPOINT`, `DATAFORGE_COSMOS_KEY`, `DATAFORGE_COSMOS_DATABASE` |

Cloud credentials also resolve from each provider's default chain (IAM
instance roles, Application Default Credentials, managed identity), so on
EC2/GKE/AKS you usually only need the bucket/table names.
`GET /v1/admin/health` reports which backends are active.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `DATAFORGE_SECRET_KEY` | dev value | JWT signing — **must** change in production |
| `DATAFORGE_DATABASE_URL` | sqlite | Postgres URL in production |
| `DATAFORGE_STORAGE_BACKEND` | local | `s3` \| `gcs` \| `azure` object storage (see Option D) |
| `DATAFORGE_NOSQL_BACKEND` | local | `dynamodb` \| `mongodb` \| `firestore` \| `cosmos` (see Option D) |
| `DATAFORGE_CELERY_BROKER_URL` | — | enables distributed workers |
| `DATAFORGE_NATS_URL` | — | event streaming transport |
| `ANTHROPIC_API_KEY` | — | enables LLM-enhanced agents |
| `DATAFORGE_LLM_BUDGET_USD_PER_PROJECT` | 25.0 | hard agent-spend ceiling |
| `DATAFORGE_RESPECT_ROBOTS_TXT` | true | never disable in production |

## Operational checklist

- [ ] Rotate `DATAFORGE_SECRET_KEY`; store secrets in a manager
- [ ] TLS terminate at the ingress; serve the web app over HTTPS only
- [ ] Postgres backups + S3 lifecycle policies for raw artifacts
- [ ] Alert on `pipeline.failed` / `alert.raised` events
- [ ] Review plugin permissions before enabling installations
