"""DataForge V2 API entrypoint.

Run (from the dataforge/ directory):
    uvicorn apps.api.main:app --reload --port 8000
"""
from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from backend import __version__
from backend.api.v1 import router as v1_router
from backend.core.config import get_settings
from backend.db.base import init_db

logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)

settings = get_settings()

app = FastAPI(
    title=settings.api_title,
    version=__version__,
    description="Autonomous multimodal dataset curation platform — control plane API.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.env == "development" else [],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?" if settings.env != "development" else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Response-Time-Ms"] = f"{(time.perf_counter() - start) * 1000:.1f}"
    rate = getattr(request.state, "rate_limit", None)
    if rate:
        response.headers["X-RateLimit-Limit"] = str(rate[0])
        response.headers["X-RateLimit-Remaining"] = str(rate[1])
    return response


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/")
def root():
    return {"name": "DataForge V2", "version": __version__, "docs": "/docs", "api": "/v1"}


app.include_router(v1_router)
