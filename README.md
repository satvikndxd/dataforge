<div align="center">
  <h1 align="center">DataForge</h1>
  <p align="center">
    <strong>Universal Multimodal AI Dataset Extraction & Synthesis Engine</strong>
  </p>
  <p align="center">
    <a href="https://github.com/satvikndxd/dataforge/actions/workflows/dataforge-v2.yml"><img src="https://github.com/satvikndxd/dataforge/actions/workflows/dataforge-v2.yml/badge.svg" alt="DataForge V2 CI" /></a>
    <a href="https://github.com/satvikndxd/dataforge/actions/workflows/backend-tests.yml"><img src="https://github.com/satvikndxd/dataforge/actions/workflows/backend-tests.yml/badge.svg" alt="Backend Tests" /></a>
    <img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python 3.11+" />
    <img src="https://img.shields.io/badge/next.js-TypeScript-black" alt="Next.js" />
    <img src="https://img.shields.io/badge/tests-33%2F33%20passing-brightgreen" alt="Tests" />
  </p>
</div>

---

DataForge turns a research goal into a clean, versioned, ML-ready dataset. It scrapes, extracts, cleans, deduplicates, quality-scores, and packages raw web data across **four modalities — text, audio, imagery, and relational graphs** — with provable lineage from every record back to its source URL.

This repository contains **two generations** of the system:

| Generation | Path | Description |
|---|---|---|
| **DataForge V2** (current) | [`dataforge/`](dataforge/) | Autonomous dataset supply chain: 19 governed agents, an 11-stage pipeline, 12-dimension quality scoring, 4-layer dedup, versioned datasets, plugins, SDKs, and a Bauhaus-style Next.js web app. Zero-infra by default (SQLite + local FS), scales to Postgres/Redis/NATS/S3/Qdrant/Neo4j via env vars alone. |
| **DataForge V1** (legacy) | [`backend/`](backend/) + [`frontend/`](frontend/) | The original FastAPI scraping engine + dark-mode Next.js UI. Modality-specific extraction (TF-IDF text curation, STT audio + spectrograms, image harvesting, NetworkX knowledge graphs) with ZIP export pipelines. |

---

## 📊 Project at a Glance

All numbers below are **measured from this repository** (commit-accurate as of 2026-08-08).

| Metric | Value |
|---|---|
| Tracked files | **149** |
| Python source | **~7,800 lines** across 68 files |
| TypeScript / TSX source | **~3,500 lines** across 25 files |
| Documentation | **10 Markdown docs**, ~520 lines |
| V2 REST API surface | **44 operations** over 39 paths (26 GET · 15 POST · 1 PATCH · 1 DELETE · 1 download stream) |
| V1 REST API surface | **11 endpoints** (scrape, clean, export per modality) |
| Autonomous agents (V2) | **19** (research → publish, per spec §5.3) |
| Pipeline stages (V2) | **11** — discover · fetch · extract · chunk · embed · dedup · score · graphify · document · version · publish |
| Quality sub-scores (V2) | **12** — completeness, freshness, uniqueness, readability, authority, language quality, metadata richness, bias risk, safety, coverage, representativeness, citation quality |
| Deduplication layers (V2) | **4** — exact hash · URL canonicalization · MinHash · semantic |
| Export formats (V2) | **6** — JSONL, JSON, CSV, Parquet, SQLite, HF bundle |
| Plugins | **3** shipped (arXiv + Wikipedia sources, WebDataset exporter) |
| SDKs | **2** — Python (`dataforge_sdk.py`, 128 LOC) + TypeScript (`index.ts`, 101 LOC) |
| Web UI pages | **12** (V2 Bauhaus app) + legacy V1 dashboard |
| CI workflows | **2** GitHub Actions (V2 backend + web, V1 backend) |

## ✅ Test & Runtime Measurements

Verified locally on Python 3.11 before this commit:

| Measurement | Result |
|---|---|
| V2 test suite (`dataforge/tests`) | **33 / 33 passing** in **~1.7 s** (29 unit + 4 integration) |
| Unit coverage areas | dedup layers, quality scoring, event bus + chunking, security (auth/tenancy) |
| Integration coverage | full dataset flow (project → pipeline → version → export), agent registry & governance, auth + multi-tenancy isolation |
| API cold boot (uvicorn, SQLite) | ready in **< 4 s** |
| `GET /` root response | **200 OK in ~3 ms** (local) |
| OpenAPI schema | `DataForge V2 API v2.0.0` — 39 paths / 44 operations, self-documented at `/docs` |

Reproduce:

```bash
cd dataforge
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt pytest
python -m pytest tests -q          # → 33 passed
uvicorn apps.api.main:app --port 8000
curl -s -o /dev/null -w '%{http_code} %{time_total}s\n' localhost:8000/
```

---

## 🏗️ Architecture (V2)

```
goal ──▶ Research/Search/Scraping agents ──▶ discover → fetch → extract
                                                 │
         quality gates + human review ◀── score ◀┤ chunk → embed → dedup
                                                 │
         publish ◀── version ◀── document ◀── graphify
```

- **Planes:** control (`apps/api`), agent (`backend/agents`), data (`backend/pipelines`, `backend/services`, `backend/storage`, `backend/workers`), intelligence (`backend/intelligence` — LLM router, embeddings, vector index), governance (budgets, approval gates, audit trail).
- **Quality as an artifact:** every chunk gets 12 sub-scores; publishing is gated behind quality thresholds **and** human approval via active-learning-prioritized review queues.
- **Provenance:** immutable dataset versions with content hashes, manifests, auto-generated dataset cards, and lineage to every source URL.
- **Storage:** content-addressed object store (local FS by default, S3/MinIO via `DATAFORGE_STORAGE_BACKEND=s3`).
- **LLM-optional:** set `ANTHROPIC_API_KEY` for LLM-enhanced planning/metadata/evaluation; everything degrades to deterministic heuristics without it.

Deep dives: [`dataforge/docs/architecture/overview.md`](dataforge/docs/architecture/overview.md) · [`dataforge/docs/api/reference.md`](dataforge/docs/api/reference.md) · [deployment guide](dataforge/docs/guides/deployment.md) · [developer guide](dataforge/docs/guides/developer.md) · [plugin docs](dataforge/docs/plugins/).

## 📁 Repository Map

```
├── dataforge/            # DataForge V2 — current platform
│   ├── apps/api/         #   FastAPI entrypoint (OpenAPI at /docs)
│   ├── apps/web/         #   Next.js Bauhaus UI (12 pages, :3100)
│   ├── backend/          #   agents · pipelines · services · storage · intelligence · events · workers · db
│   ├── packages/         #   Python + TypeScript SDKs, JSON Schema contracts
│   ├── plugins/          #   sources (arxiv, wikipedia) · exporters (webdataset)
│   ├── infra/            #   Docker, docker-compose, Helm, CI templates
│   ├── tests/            #   29 unit + 4 integration tests
│   └── docs/             #   architecture, API reference, guides
├── backend/              # DataForge V1 — FastAPI scraping engine (11 endpoints, 9 processors)
├── frontend/             # DataForge V1 — Next.js dark-mode UI
└── .github/workflows/    # CI: dataforge-v2.yml, backend-tests.yml
```

---

## 🚀 Quickstart

### DataForge V2 (recommended)

```bash
# Backend (Python 3.11+)
cd dataforge
pip install -r requirements.txt
uvicorn apps.api.main:app --port 8000        # OpenAPI docs at http://localhost:8000/docs

# Web (Node 18+) — new terminal
cd dataforge/apps/web
npm install && npm run dev                    # Bauhaus UI at http://localhost:3100

# Or everything at once
docker compose -f dataforge/infra/compose/docker-compose.yml up
```

Open http://localhost:3100, create an organization, and launch a pipeline from the Builder.

**60-second SDK demo:**

```python
from packages.sdk.python.dataforge_sdk import DataForge

df = DataForge("http://localhost:8000")
df.register("My Org", "me@example.com", "s3cret-pass")
project = df.create_project("Runology", goal="Nordic runology reference dataset")
df.add_inline_source(project["id"], "Primer", open("primer.txt").read())
```

### DataForge V1 (legacy)

Requires `ffmpeg` for the audio/spectrogram pipeline (`brew install ffmpeg` on macOS).

```bash
# Backend
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000

# Frontend — new terminal
cd frontend
npm install && npm run dev                    # UI at http://localhost:3000
```

## 🧪 Continuous Integration

Every push and PR runs two workflows:

- **[DataForge V2 CI](.github/workflows/dataforge-v2.yml)** — Python 3.11: unit + integration suites (`pytest tests/unit`, `pytest tests/integration`) plus a web build, on any change under `dataforge/`.
- **[Backend Tests](.github/workflows/backend-tests.yml)** — legacy V1 backend suite on any change under `backend/`.

## 💻 Tech Stack

| Layer | V2 | V1 |
|---|---|---|
| API | FastAPI · SQLAlchemy · Pydantic | FastAPI · Uvicorn |
| Frontend | Next.js (TS) · Tailwind (Bauhaus design system) | Next.js (TS) · Tailwind · glassmorphic dark UI |
| Storage | SQLite → Postgres · local FS → S3/MinIO · optional Redis/NATS/Qdrant/Neo4j/Celery | Local FS + ZIP exports |
| Intelligence | Anthropic Claude (optional) · local embeddings · vector index | scikit-learn/NLTK TF-IDF · SpeechRecognition + pydub/ffmpeg · NetworkX |

---

<div align="center">
  <p>Built for automated intelligence — measured, versioned, and governed.</p>
</div>
