# API Reference (/v1)

Interactive OpenAPI docs live at `http://localhost:8000/docs`.

## Authentication

- `POST /v1/auth/register` — bootstrap org + Owner `{org_name, email, password}`
- `POST /v1/auth/login` / `POST /v1/auth/refresh`
- `POST /v1/api-keys` (Admin+) — returns plaintext key once; use header `X-API-Key`
- JWTs: `Authorization: Bearer <access_token>` (1h TTL, refresh 14d)

## Core resources

| Method + path | Role | Notes |
|---|---|---|
| `POST /v1/projects` | Builder | `{name, goal, modality, config}` |
| `GET /v1/projects` | any | cursor pagination (`cursor`, `limit`) |
| `POST /v1/sources` | Builder | types: url, inline, file, rss, wikipedia, arxiv |
| `POST /v1/pipelines/run` | Builder | async; returns `{run_id}` (202) |
| `GET /v1/runs/{id}` | any | stages, stats, error |
| `GET /v1/runs/{id}/events` | any | durable event trail |
| `GET /v1/runs/{id}/events/stream` | any | SSE (replay + live, keepalives) |
| `POST /v1/runs/{id}/cancel` | Builder | cooperative cancel |
| `GET /v1/datasets` / `GET /v1/datasets/{id}` | any | versions embedded |
| `GET /v1/datasets/{id}/versions/{vid}` | any | manifest, card, gates, samples |
| `POST /v1/datasets/{id}/publish` | Admin | 409 if quality gates fail |
| `POST /v1/exports` | Builder | jsonl, json, csv, parquet, sqlite, hf |
| `GET /v1/exports/{id}/download` | any | checksummed artifact |
| `GET /v1/agents` | any | catalog with tiers + approval flags |
| `POST /v1/agents/{name}/invoke` | Builder | gated agents park as `pending_approval` |
| `POST /v1/agent-runs/{id}/approve` / `reject` | Admin | approval gates |
| `GET /v1/reviews` / `POST /v1/reviews/{id}` | Reviewer | active-learning priority order |
| `GET /v1/graph?project_id=` | any | entities + confidence-scored edges |
| `GET /v1/plugins/available` / `POST /v1/plugins` | Admin | manifest validation |
| `GET /v1/admin/health` `metrics` `audit-logs` `usage` | varies | observability |

## Conventions

- Cursor pagination: `{"items": [...], "next_cursor": "...", "has_more": true}`
- Rate limits: 429 with `Retry-After`; headers `X-RateLimit-Limit/-Remaining`
- Errors: `{"detail": "..."}` with conventional status codes
- All queries are org-scoped; cross-tenant access is a 404 by construction
