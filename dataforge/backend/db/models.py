"""System-of-record schema (spec §8).

Principles: multi-tenant by organization, immutable events/audit, versioned
datasets, content-addressed artifacts, strong lineage, JSON for flexible
metadata.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255), unique=True)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    password_hash: Mapped[str] = mapped_column(String(512))
    role: Mapped[str] = mapped_column(String(32), default="builder")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(255))
    key_hash: Mapped[str] = mapped_column(String(128), index=True)
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    goal: Mapped[str] = mapped_column(Text, default="")
    modality: Mapped[str] = mapped_column(String(32), default="text")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(48), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    current_version_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(48), index=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    version: Mapped[str] = mapped_column(String(32))          # e.g. "1.0.0"
    status: Mapped[str] = mapped_column(String(32), default="draft")  # draft|pending_approval|published
    manifest: Mapped[dict] = mapped_column(JSON, default=dict)
    quality_report: Mapped[dict] = mapped_column(JSON, default=dict)
    dataset_card: Mapped[str] = mapped_column(Text, default="")
    content_hash: Mapped[str] = mapped_column(String(128), default="")
    pipeline_run_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(48), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    type: Mapped[str] = mapped_column(String(32))  # url|wikipedia|arxiv|inline|rss|file
    uri: Mapped[str] = mapped_column(Text, default="")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="active")  # active|quarantined|restricted
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(48), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    dataset_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")  # queued|running|succeeded|failed|cancelled
    stages: Mapped[list] = mapped_column(JSON, default=list)     # [{name,status,started,finished,detail}]
    current_stage: Mapped[str] = mapped_column(String(48), default="")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(48), index=True)
    project_id: Mapped[str] = mapped_column(String(48), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    run_id: Mapped[str | None] = mapped_column(String(48), index=True, nullable=True)
    url: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(Text, default="")
    content_hash: Mapped[str] = mapped_column(String(128), index=True)
    mime_type: Mapped[str] = mapped_column(String(128), default="text/plain")
    storage_key: Mapped[str] = mapped_column(Text, default="")       # raw artifact
    text_storage_key: Mapped[str] = mapped_column(Text, default="")  # extracted text
    language: Mapped[str] = mapped_column(String(16), default="en")
    license_hint: Mapped[str] = mapped_column(String(64), default="unknown")
    license_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(32), default="fetched")  # fetched|cleaned|rejected|duplicate|quarantined
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    __table_args__ = (Index("ix_documents_run_hash", "run_id", "content_hash"),)


class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(48), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    run_id: Mapped[str | None] = mapped_column(String(48), index=True, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text)
    token_estimate: Mapped[int] = mapped_column(Integer, default=0)
    embedding_id: Mapped[str] = mapped_column(String(64), default="")
    scores: Mapped[dict] = mapped_column(JSON, default=dict)     # per-record quality sub-scores
    status: Mapped[str] = mapped_column(String(32), default="active")  # active|duplicate|rejected|needs_review
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class QualityReport(Base):
    __tablename__ = "quality_reports"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(48), index=True)
    dataset_version_id: Mapped[str | None] = mapped_column(String(48), index=True, nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(48), index=True, nullable=True)
    scores: Mapped[dict] = mapped_column(JSON, default=dict)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    gates: Mapped[dict] = mapped_column(JSON, default=dict)      # gate -> pass/fail
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(48), index=True)
    project_id: Mapped[str | None] = mapped_column(String(48), index=True, nullable=True)
    pipeline_run_id: Mapped[str | None] = mapped_column(String(48), index=True, nullable=True)
    agent_name: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="running")  # running|succeeded|failed|pending_approval|rejected
    input: Mapped[dict] = mapped_column(JSON, default=dict)
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ReviewItem(Base):
    __tablename__ = "review_items"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(48), index=True)
    project_id: Mapped[str] = mapped_column(String(48), index=True)
    run_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    subject_type: Mapped[str] = mapped_column(String(32))  # chunk|document|dataset_version|agent_action
    subject_id: Mapped[str] = mapped_column(String(48), index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[float] = mapped_column(Float, default=0.5)  # active-learning priority
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending|approved|rejected
    resolution: Mapped[dict] = mapped_column(JSON, default=dict)
    reviewer_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ExportJob(Base):
    __tablename__ = "export_jobs"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(48), index=True)
    dataset_version_id: Mapped[str] = mapped_column(String(48), index=True)
    format: Mapped[str] = mapped_column(String(32))  # jsonl|json|csv|parquet|sqlite|hf
    status: Mapped[str] = mapped_column(String(32), default="queued")
    storage_key: Mapped[str] = mapped_column(Text, default="")
    checksum: Mapped[str] = mapped_column(String(128), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(48), index=True)
    actor: Mapped[str] = mapped_column(String(128))   # user:usr_… | agent:research | system
    action: Mapped[str] = mapped_column(String(128), index=True)
    resource_type: Mapped[str] = mapped_column(String(64), default="")
    resource_id: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


class EventRecord(Base):
    """Durable copy of every bus event (replayable audit stream)."""

    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(48), index=True, default="")
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    run_id: Mapped[str | None] = mapped_column(String(48), index=True, nullable=True)
    actor: Mapped[str] = mapped_column(String(128), default="system")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


class GraphEntity(Base):
    __tablename__ = "graph_entities"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(48), index=True)
    project_id: Mapped[str] = mapped_column(String(48), index=True)
    name: Mapped[str] = mapped_column(String(512), index=True)
    entity_type: Mapped[str] = mapped_column(String(64), default="concept")
    canonical_key: Mapped[str] = mapped_column(String(512), index=True)
    mentions: Mapped[int] = mapped_column(Integer, default=1)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class GraphRelation(Base):
    __tablename__ = "graph_relations"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(48), index=True)
    project_id: Mapped[str] = mapped_column(String(48), index=True)
    source_entity_id: Mapped[str] = mapped_column(String(48), index=True)
    target_entity_id: Mapped[str] = mapped_column(String(48), index=True)
    relation: Mapped[str] = mapped_column(String(128), default="related_to")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    evidence_document_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class PluginInstallation(Base):
    __tablename__ = "plugin_installations"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(48), index=True)
    name: Mapped[str] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(32), default="0.0.0")
    plugin_type: Mapped[str] = mapped_column(String(32))
    manifest: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
