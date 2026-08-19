"""Central configuration.

Every external system is optional: DataForge boots with zero infrastructure
(SQLite + local FS + in-memory bus/queue/vector/graph) and upgrades to
Postgres/Redis/NATS/Qdrant/Neo4j/Celery, cloud object storage (AWS S3, GCS,
Azure Blob), and NoSQL stores (DynamoDB, MongoDB, Firestore, Cosmos DB)
purely through environment variables. This keeps `docker compose up` and
bare `uvicorn` both viable.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATAFORGE_", env_file=".env", extra="ignore")

    # --- app ---
    env: str = "development"
    debug: bool = False
    api_title: str = "DataForge V2 API"
    api_version: str = "v1"
    secret_key: str = Field(default="dataforge-dev-secret-change-me")
    access_token_ttl_seconds: int = 60 * 60  # 1h
    refresh_token_ttl_seconds: int = 60 * 60 * 24 * 14  # 14d

    # --- system of record ---
    database_url: str = "sqlite:///./dataforge.db"

    # --- cache / queue broker (optional) ---
    redis_url: str | None = None
    celery_broker_url: str | None = None

    # --- event streaming (optional) ---
    nats_url: str | None = None

    # --- object storage ---
    storage_backend: str = "local"  # local | s3 | gcs | azure
    storage_root: str = "./storage"
    # AWS S3 / MinIO
    s3_endpoint: str | None = None
    s3_bucket: str = "dataforge"
    s3_region: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    # Google Cloud Storage
    gcs_bucket: str = "dataforge"
    gcs_project: str | None = None
    gcs_credentials_file: str | None = None  # falls back to GOOGLE_APPLICATION_CREDENTIALS
    # Azure Blob Storage
    azure_container: str = "dataforge"
    azure_connection_string: str | None = None
    azure_account_url: str | None = None  # https://<account>.blob.core.windows.net
    azure_account_key: str | None = None

    # --- NoSQL document / key-value store (optional) ---
    nosql_backend: str = "local"  # local | dynamodb | mongodb | firestore | cosmos
    # AWS DynamoDB
    dynamodb_table: str = "dataforge"
    dynamodb_region: str | None = None
    dynamodb_endpoint: str | None = None  # e.g. http://localhost:8000 for DynamoDB Local
    dynamodb_access_key: str | None = None  # falls back to default AWS credential chain
    dynamodb_secret_key: str | None = None
    # MongoDB (or any wire-compatible NoSQL, e.g. DocumentDB / Cosmos Mongo API)
    mongodb_url: str | None = None
    mongodb_database: str = "dataforge"
    # GCP Firestore
    firestore_project: str | None = None
    firestore_collection_prefix: str = "dataforge"
    firestore_credentials_file: str | None = None
    # Azure Cosmos DB (Core/SQL API)
    cosmos_endpoint: str | None = None
    cosmos_key: str | None = None
    cosmos_database: str = "dataforge"
    cosmos_container: str = "items"

    # --- vector / graph (optional) ---
    qdrant_url: str | None = None
    neo4j_url: str | None = None
    neo4j_user: str = "neo4j"
    neo4j_password: str | None = None

    # --- intelligence ---
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    llm_default_model: str = "claude-opus-4-8"
    llm_cheap_model: str = "claude-haiku-4-5"
    llm_max_tokens: int = 2048
    llm_budget_usd_per_project: float = 25.0
    embedding_dim: int = 256

    # --- pipeline / scraping policy ---
    respect_robots_txt: bool = True
    fetch_timeout_seconds: float = 20.0
    fetch_max_concurrency: int = 8
    domain_rate_limit_seconds: float = 1.0
    user_agent: str = "DataForgeBot/2.0 (+https://github.com/dataforge; dataset curation; respects robots.txt)"
    max_document_bytes: int = 10 * 1024 * 1024

    # --- quality gates (defaults; overridable per project) ---
    gate_min_safety: float = 0.8
    gate_max_duplicate_fraction: float = 0.25
    gate_min_license_confidence: float = 0.6
    review_score_threshold: float = 0.5  # records below this go to human review

    # --- rate limiting ---
    rate_limit_per_minute: int = 240

    @property
    def storage_path(self) -> Path:
        p = Path(self.storage_root)
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Test helper: re-read environment on next access."""
    get_settings.cache_clear()
    os.environ.setdefault("DATAFORGE_ENV", "development")
