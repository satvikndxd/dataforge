# Architecture Overview

DataForge V2 is a **modular monolith** with clean plane separation, designed to
split into services only when scale demands it.

## Planes

| Plane | Modules | Responsibility |
|---|---|---|
| Experience | `apps/web` | Bauhaus UI: builder, visualizer, browser, monitor, review |
| Control | `backend/api`, `apps/api` | /v1 REST, auth, RBAC, rate limits, SSE |
| Agent | `backend/agents` | 19 typed agents + governed runtime (budgets, approvals, audit) |
| Data | `backend/pipelines`, `backend/services`, `backend/storage`, `backend/workers` | 11-stage pipeline, extraction, dedup, exports, object store, task queue |
| Intelligence | `backend/intelligence` | embeddings, vector index, LLM router, knowledge graph |
| Governance | `backend/events`, review/audit services | durable events, audit logs, review queues, quality gates |

## Event flow

Every pipeline run is a checkpointed state machine. Each stage emits
`pipeline.stage.started/completed`; agents emit `agent.run.*`; governance
handlers mirror sensitive events into `audit_logs`; every event is persisted
in the `events` table (replayable) and fanned out to SSE subscribers.

```
create_run ─► queued ─► running ─► [discover → fetch → extract → chunk →
  embed → dedup → score → graphify → document → version → publish]
  ─► succeeded | failed | cancelled
```

## Storage model

- **System of record** — SQLAlchemy (SQLite default, Postgres in production).
- **Artifacts** — content-addressed object store (`orgs/<org>/<cat>/<sha>`):
  raw bytes, extracted text, cleaned text, export bundles.
- **Vectors** — in-memory index by default; Qdrant adapter for scale.
- **Graph** — relational entity/edge tables; Neo4j adapter for traversal-heavy
  workloads.

## Failure recovery

- Stage failures mark the run + stage failed with the error attached; all
  prior artifacts and lineage survive for diagnosis.
- Agents have `recover()` hooks; scraping quarantines paywalls/captchas
  instead of retry-hammering.
- Celery deployments get retries with exponential backoff + DLQ semantics;
  the local queue keeps the same task signatures.

## Scaling path (spec §15)

1. Move DATABASE_URL to Postgres, storage to S3/MinIO.
2. Enable Celery workers per queue class (`ingest.*`, `ai.*`, `export.*`).
3. Switch bus transport to NATS JetStream (same envelope + subjects).
4. Swap vector index to Qdrant, graph to Neo4j.
5. Scale API pods statelessly behind an ingress (Helm chart included).
