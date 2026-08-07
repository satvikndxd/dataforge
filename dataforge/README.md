# DataForge V2

**Autonomous multimodal dataset curation for modern AI systems.**

DataForge V2 is a dataset supply chain: discovery → extraction → cleaning →
enrichment → deduplication → quality scoring → knowledge structuring →
packaging → evaluation → publishing — with provable lineage, quality gates,
and human oversight at every step.

## Features

- **Autonomous research pipeline** — Research/Search/Scraping agents expand a
  goal into queries, discover sources (robots-aware, paywall/captcha quarantine)
  and extract content.
- **Quality as a first-class artifact** — 12 sub-score formulas (completeness,
  freshness, uniqueness, readability, authority, language quality, metadata
  richness, bias risk, safety, coverage, representativeness, citation quality),
  quality gates, PII detection/redaction.
- **4-layer deduplication** — exact hash, URL canonicalization, MinHash, semantic.
- **19 governed agents** — durable runs, per-project budgets, approval gates,
  full audit trail.
- **Versioned datasets** — immutable versions with content hashes, manifests,
  auto-generated dataset cards and lineage back to every source URL.
- **Human-in-the-loop** — active-learning-prioritized review queues; publishing
  is gated behind quality gates + human approval.
- **Knowledge graphs** — entity/relation extraction with confidence pruning.
- **Exports** — JSONL, JSON, CSV, Parquet, SQLite, Hugging Face-style bundles.
- **Plugin-first** — manifest-validated source/extractor/scorer/exporter/agent
  plugins with declared permissions.
- **Zero-infra default** — boots on SQLite + local FS + in-process bus/queue;
  upgrades to Postgres/Redis/NATS/S3/Qdrant/Neo4j/Celery via env vars alone.

## Quickstart

```bash
# backend (Python 3.11+)
pip install -r requirements.txt
uvicorn apps.api.main:app --port 8000     # OpenAPI docs at /docs

# web (Node 18+)
cd apps/web && npm install && npm run dev # Bauhaus UI at :3100

# or everything at once
docker compose -f infra/compose/docker-compose.yml up
```

Then open http://localhost:3100, create an organization, and launch a pipeline
from the Builder. Set `ANTHROPIC_API_KEY` to enable LLM-enhanced planning,
metadata and evaluation (everything degrades to deterministic heuristics
without it).

### 60-second SDK demo

```python
from packages.sdk.python.dataforge_sdk import DataForge

df = DataForge("http://localhost:8000")
df.register("My Org", "me@example.com", "s3cret-pass")
project = df.create_project("Runology", goal="Nordic runology reference dataset")
df.add_inline_source(project["id"], "Primer", open("primer.txt").read())
run = df.wait_for_run(df.run_pipeline(project["id"], auto_discover=False)["run_id"])
version = df.latest_version(run["dataset_id"])
df.export(version["id"], "jsonl", path="dataset.jsonl")
```

## Architecture

```
Next.js Bauhaus UI ──► FastAPI /v1 control plane ──► Event bus (durable)
                          │                              │
                          ▼                              ▼
                   Pipeline engine ──► 19 governed agents ──► audit/budget/approvals
                          │
                          ▼
       SQLite/Postgres · local FS/S3 · vector index/Qdrant · graph/Neo4j
```

Monorepo layout: `backend/` (modular monolith: core, db, events, storage,
intelligence, services, agents, pipelines, workers, api), `apps/` (api
entrypoint + web), `plugins/`, `packages/` (SDKs), `infra/` (Docker, Compose,
Helm, CI), `docs/`, `tests/`.

## Testing

```bash
python -m pytest tests -q     # 33 tests: unit formulas + full API lifecycle
```

## License

Apache-2.0
