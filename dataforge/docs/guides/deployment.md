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

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `DATAFORGE_SECRET_KEY` | dev value | JWT signing — **must** change in production |
| `DATAFORGE_DATABASE_URL` | sqlite | Postgres URL in production |
| `DATAFORGE_STORAGE_BACKEND` | local | `s3` + S3 vars for MinIO/S3 |
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
