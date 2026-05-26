# DataForge Deployment Guide

DataForge runs as **two services on [Railway](https://railway.app)** (nixpacks builds):

1. **backend** — FastAPI / Uvicorn (`backend/`)
2. **frontend** — Next.js (`frontend/`)

The frontend does **not** call the backend directly from the browser. `next.config.mjs`
rewrites `/api/:path*` to `${NEXT_PUBLIC_API_URL}/api/:path*`, so API calls are proxied
**server-side** by the Next.js server. The browser only ever talks to the frontend origin.

```
browser ──► frontend (Next.js)  ──proxy /api/*──►  backend (FastAPI)
```

---

## Backend service

**Build:** configured by `backend/nixpacks.toml` / `backend/railway.toml`.

- System package: `ffmpeg` (required by `pydub` / `SpeechRecognition` for audio).
- `pip install -r requirements.txt`
- `python -m spacy download en_core_web_sm` (required for the Graph modality NER).

**Start command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`

**Health check:** `GET /` returns `{"message": "DataForge Backend is operational"}`.
A dependency-free `GET /health` is also available (`{"status": "healthy", ...}`).

### Backend environment variables
| Variable | Required | Default | Notes |
|---|---|---|---|
| `PORT` | provided by Railway | `8000` | Bind port. |
| `CORS_ORIGINS` | recommended | `http://localhost:3000,http://127.0.0.1:3000` | Comma-separated allowed origins. In production set to your frontend's public URL, e.g. `https://dataforge-frontend.up.railway.app`. |

> Note: because the frontend proxies `/api/*` server-side, cross-origin browser calls
> to the backend are not part of the normal flow. Still set `CORS_ORIGINS` to your
> frontend origin so any direct browser access is restricted rather than wide open.

---

## Frontend service

**Build:** configured by `frontend/nixpacks.toml` / `frontend/railway.toml`
(`npm install && npm run build`).

**Start command:** `npm run start -- -p $PORT`

**Health check:** `GET /`.

### Frontend environment variables
| Variable | Required | Default | Notes |
|---|---|---|---|
| `PORT` | provided by Railway | `3000` | Bind port. |
| `NEXT_PUBLIC_API_URL` | **yes (prod)** | `http://127.0.0.1:8000` | Public URL of the **backend** service, e.g. `https://dataforge-backend.up.railway.app`. Used by the Next.js `/api/*` rewrite. |

---

## Deploy order (first time)
1. Deploy the **backend** service; note its public URL.
2. Set the frontend's `NEXT_PUBLIC_API_URL` to that backend URL.
3. Set the backend's `CORS_ORIGINS` to the frontend's public URL.
4. Deploy/redeploy the **frontend**.

---

## Continuous Integration

CI definitions live in [`ci-templates/`](./ci-templates/) (not `.github/workflows/`,
because the automated push token lacks the GitHub `workflow` scope). To enable CI,
copy them into `.github/workflows/` — see [`ci-templates/README.md`](./ci-templates/README.md).

- **backend-tests** — Python 3.11 + ffmpeg, `pip install -r requirements-dev.txt`, `pytest --cov`.
- **frontend-tests** — Node 20, `npm ci`, `next lint`, `next build`.

---

## Local development

```bash
# Backend
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm   # for the Graph modality
# ffmpeg must be installed on your machine for the Audio modality (e.g. brew install ffmpeg)
uvicorn main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev   # http://localhost:3000, proxies /api/* to http://127.0.0.1:8000

# Backend tests
cd backend
pip install -r requirements-dev.txt
pytest
```
