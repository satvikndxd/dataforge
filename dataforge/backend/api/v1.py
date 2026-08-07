"""DataForge /v1 REST API (spec §9).

RESTful resources, cursor pagination, async job handles, SSE streaming,
rate-limit headers, org-scoped tenancy on every query.
"""
from __future__ import annotations

import asyncio
import base64
import json
import queue as queue_mod
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field

from backend.agents.runtime import (
    AgentContext,
    approve_agent_run,
    get_agent_registry,
    invoke_agent,
    reject_agent_run,
)
from backend.api.deps import Principal, get_principal, rate_limit, require_role
from backend.core.ids import new_id
from backend.core.security import Role, decode_token
from backend.db.base import session_scope
from backend.db.models import (
    AgentRun,
    AuditLog,
    Chunk,
    Dataset,
    DatasetVersion,
    Document,
    EventRecord,
    ExportJob,
    Organization,
    PipelineRun,
    Project,
    QualityReport,
    ReviewItem,
    Source,
    User,
)
from backend.events.bus import get_event_bus
from backend.services import exports as export_service
from backend.services import graph as graph_service
from backend.services import identity, plugins as plugin_service
from backend.services.review import resolve_review
from backend.pipelines.engine import STAGES, cancel_run, create_run, start_run_async
from backend.workers.queue import get_task_queue

router = APIRouter(prefix="/v1")


# ---------------------------------------------------------------------------
# Pagination helpers (cursor = base64("<created_at_iso>|<id>"))
# ---------------------------------------------------------------------------


def _encode_cursor(created_at: datetime, row_id: str) -> str:
    return base64.urlsafe_b64encode(f"{created_at.isoformat()}|{row_id}".encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, str] | None:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        ts, row_id = raw.split("|", 1)
        return datetime.fromisoformat(ts), row_id
    except Exception:
        return None


def _paginate(query_rows: list, limit: int, serializer) -> dict:
    has_more = len(query_rows) > limit
    rows = query_rows[:limit]
    next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id) if has_more and rows else None
    return {"items": [serializer(r) for r in rows], "next_cursor": next_cursor, "has_more": has_more}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class RegisterBody(BaseModel):
    org_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8)
    name: str = ""


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class RefreshBody(BaseModel):
    refresh_token: str


@router.post("/auth/register", status_code=201, tags=["auth"])
def register(body: RegisterBody):
    try:
        return identity.register(body.org_name, body.email, body.password, body.name)
    except identity.IdentityError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/auth/login", tags=["auth"])
def login(body: LoginBody):
    try:
        return identity.login(body.email, body.password)
    except identity.IdentityError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


@router.post("/auth/refresh", tags=["auth"])
def refresh(body: RefreshBody):
    claims = decode_token(body.refresh_token)
    if claims is None or claims.kind != "refresh":
        raise HTTPException(status_code=401, detail="invalid refresh token")
    return identity.refresh(claims.sub, claims.org, claims.role)


class ApiKeyBody(BaseModel):
    name: str = "default"
    scopes: list[str] = ["*"]


@router.post("/api-keys", status_code=201, tags=["auth"])
def create_api_key(body: ApiKeyBody, principal: Principal = Depends(require_role(Role.ADMIN))):
    return identity.create_key(principal.org_id, principal.user_id, body.name, body.scopes)


@router.get("/api-keys", tags=["auth"])
def list_api_keys(principal: Principal = Depends(get_principal)):
    from backend.db.models import ApiKey

    with session_scope() as session:
        rows = session.query(ApiKey).filter_by(org_id=principal.org_id, revoked=False).all()
        return {"items": [{"id": r.id, "name": r.name, "scopes": r.scopes,
                           "created_at": r.created_at} for r in rows]}


@router.delete("/api-keys/{key_id}", tags=["auth"])
def revoke_api_key(key_id: str, principal: Principal = Depends(require_role(Role.ADMIN))):
    from backend.db.models import ApiKey

    with session_scope() as session:
        row = session.get(ApiKey, key_id)
        if row is None or row.org_id != principal.org_id:
            raise HTTPException(status_code=404, detail="api key not found")
        row.revoked = True
    return {"id": key_id, "revoked": True}


# ---------------------------------------------------------------------------
# Orgs / Projects
# ---------------------------------------------------------------------------


@router.get("/orgs", tags=["orgs"])
def get_org(principal: Principal = Depends(get_principal)):
    with session_scope() as session:
        org = session.get(Organization, principal.org_id)
        users = session.query(User).filter_by(org_id=principal.org_id).all()
        return {"id": org.id, "name": org.name, "slug": org.slug,
                "members": [{"id": u.id, "email": u.email, "role": u.role} for u in users]}


class ProjectBody(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    goal: str = ""
    modality: str = "text"
    config: dict = Field(default_factory=dict)


@router.post("/projects", status_code=201, tags=["projects"])
def create_project(body: ProjectBody, principal: Principal = Depends(require_role(Role.BUILDER))):
    project_id = new_id("proj")
    with session_scope() as session:
        session.add(Project(id=project_id, org_id=principal.org_id, name=body.name,
                            goal=body.goal, modality=body.modality, config=body.config))
    get_event_bus().emit("project.created", tenant_id=principal.org_id,
                         project_id=project_id, actor=f"user:{principal.user_id}",
                         payload={"resource_type": "project", "resource_id": project_id})
    return {"id": project_id, "name": body.name, "goal": body.goal, "modality": body.modality}


def _project_dict(p: Project) -> dict:
    return {"id": p.id, "name": p.name, "goal": p.goal, "modality": p.modality,
            "config": p.config, "created_at": p.created_at}


@router.get("/projects", tags=["projects"])
def list_projects(principal: Principal = Depends(rate_limit),
                  cursor: str | None = None, limit: int = Query(50, le=200)):
    with session_scope() as session:
        q = session.query(Project).filter_by(org_id=principal.org_id).order_by(
            Project.created_at.desc(), Project.id.desc())
        if cursor and (decoded := _decode_cursor(cursor)):
            q = q.filter(Project.created_at <= decoded[0], Project.id != decoded[1])
        rows = q.limit(limit + 1).all()
        return _paginate(rows, limit, _project_dict)


@router.get("/projects/{project_id}", tags=["projects"])
def get_project(project_id: str, principal: Principal = Depends(get_principal)):
    with session_scope() as session:
        p = session.get(Project, project_id)
        if p is None or p.org_id != principal.org_id:
            raise HTTPException(status_code=404, detail="project not found")
        return _project_dict(p)


class ProjectPatch(BaseModel):
    name: str | None = None
    goal: str | None = None
    config: dict | None = None


@router.patch("/projects/{project_id}", tags=["projects"])
def patch_project(project_id: str, body: ProjectPatch,
                  principal: Principal = Depends(require_role(Role.BUILDER))):
    with session_scope() as session:
        p = session.get(Project, project_id)
        if p is None or p.org_id != principal.org_id:
            raise HTTPException(status_code=404, detail="project not found")
        if body.name is not None:
            p.name = body.name
        if body.goal is not None:
            p.goal = body.goal
        if body.config is not None:
            p.config = body.config
        return _project_dict(p)


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------


class SourceBody(BaseModel):
    project_id: str
    type: str = Field(pattern="^(url|inline|file|rss|wikipedia|arxiv)$")
    uri: str = ""
    config: dict = Field(default_factory=dict)


@router.post("/sources", status_code=201, tags=["sources"])
def add_source(body: SourceBody, principal: Principal = Depends(require_role(Role.BUILDER))):
    with session_scope() as session:
        project = session.get(Project, body.project_id)
        if project is None or project.org_id != principal.org_id:
            raise HTTPException(status_code=404, detail="project not found")
        source_id = new_id("src")
        session.add(Source(id=source_id, org_id=principal.org_id, project_id=body.project_id,
                           type=body.type, uri=body.uri, config=body.config))
    get_event_bus().emit("source.added", tenant_id=principal.org_id,
                         project_id=body.project_id, actor=f"user:{principal.user_id}",
                         payload={"resource_type": "source", "resource_id": source_id,
                                  "type": body.type})
    return {"id": source_id, "type": body.type, "uri": body.uri}


@router.get("/sources", tags=["sources"])
def list_sources(project_id: str, principal: Principal = Depends(get_principal)):
    with session_scope() as session:
        rows = session.query(Source).filter_by(
            org_id=principal.org_id, project_id=project_id).order_by(Source.created_at.desc()).all()
        return {"items": [{"id": s.id, "type": s.type, "uri": s.uri, "status": s.status,
                           "config": {k: v for k, v in s.config.items() if k != "text"},
                           "created_at": s.created_at} for s in rows]}


# ---------------------------------------------------------------------------
# Pipelines / Runs
# ---------------------------------------------------------------------------


class RunBody(BaseModel):
    project_id: str
    dataset_name: str = ""
    goal: str = ""
    max_sources: int = Field(default=5, ge=1, le=50)
    auto_discover: bool = True
    auto_publish: bool = False
    build_graph: bool = True
    chunk_tokens: int = Field(default=400, ge=64, le=4000)
    providers: list[str] | None = None


@router.post("/pipelines/run", status_code=202, tags=["pipelines"])
def run_pipeline(body: RunBody, principal: Principal = Depends(require_role(Role.BUILDER))):
    with session_scope() as session:
        project = session.get(Project, body.project_id)
        if project is None or project.org_id != principal.org_id:
            raise HTTPException(status_code=404, detail="project not found")
        goal = body.goal or project.goal
    run_id = create_run(
        principal.org_id, body.project_id, actor=f"user:{principal.user_id}",
        config={"goal": goal, "dataset_name": body.dataset_name or None,
                "max_sources": body.max_sources, "auto_discover": body.auto_discover,
                "auto_publish": body.auto_publish, "build_graph": body.build_graph,
                "chunk_tokens": body.chunk_tokens, "providers": body.providers},
    )
    start_run_async(run_id)
    return {"run_id": run_id, "status": "queued", "stages": STAGES}


def _run_dict(r: PipelineRun) -> dict:
    return {"id": r.id, "project_id": r.project_id, "dataset_id": r.dataset_id,
            "status": r.status, "current_stage": r.current_stage, "stages": r.stages,
            "stats": r.stats, "error": r.error, "created_at": r.created_at,
            "started_at": r.started_at, "finished_at": r.finished_at}


@router.get("/runs", tags=["pipelines"])
def list_runs(principal: Principal = Depends(get_principal),
              project_id: str | None = None, limit: int = Query(50, le=200)):
    with session_scope() as session:
        q = session.query(PipelineRun).filter_by(org_id=principal.org_id)
        if project_id:
            q = q.filter_by(project_id=project_id)
        rows = q.order_by(PipelineRun.created_at.desc()).limit(limit).all()
        return {"items": [_run_dict(r) for r in rows]}


@router.get("/runs/{run_id}", tags=["pipelines"])
def get_run(run_id: str, principal: Principal = Depends(get_principal)):
    with session_scope() as session:
        r = session.get(PipelineRun, run_id)
        if r is None or r.org_id != principal.org_id:
            raise HTTPException(status_code=404, detail="run not found")
        return _run_dict(r)


@router.post("/runs/{run_id}/cancel", tags=["pipelines"])
def cancel_pipeline_run(run_id: str, principal: Principal = Depends(require_role(Role.BUILDER))):
    try:
        changed = cancel_run(principal.org_id, run_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="run not found")
    return {"run_id": run_id, "cancelled": changed}


@router.get("/runs/{run_id}/events", tags=["pipelines"])
def run_events(run_id: str, principal: Principal = Depends(get_principal),
               limit: int = Query(200, le=1000)):
    with session_scope() as session:
        rows = (session.query(EventRecord)
                .filter_by(org_id=principal.org_id, run_id=run_id)
                .order_by(EventRecord.created_at.asc()).limit(limit).all())
        return {"items": [{"id": e.id, "event_type": e.event_type, "actor": e.actor,
                           "payload": e.payload, "created_at": e.created_at} for e in rows]}


@router.get("/runs/{run_id}/events/stream", tags=["pipelines"])
async def stream_run_events(run_id: str, principal: Principal = Depends(get_principal)):
    """Server-Sent Events stream of live run events (spec §9.4)."""
    bus = get_event_bus()
    sub = bus.subscribe(">")

    async def event_source():
        loop = asyncio.get_event_loop()
        try:
            # replay durable history first
            with session_scope() as session:
                rows = (session.query(EventRecord)
                        .filter_by(org_id=principal.org_id, run_id=run_id)
                        .order_by(EventRecord.created_at.asc()).limit(500).all())
                for e in rows:
                    yield f"event: {e.event_type}\ndata: {json.dumps({'event_type': e.event_type, 'payload': e.payload, 'replay': True}, default=str)}\n\n"
            terminal = {"pipeline.completed", "pipeline.failed"}
            idle = 0.0
            while idle < 600:
                try:
                    event = await loop.run_in_executor(None, sub.q.get, True, 2.0)
                except queue_mod.Empty:
                    idle += 2.0
                    yield ": keepalive\n\n"
                    continue
                if event.run_id != run_id or event.tenant_id != principal.org_id:
                    continue
                idle = 0.0
                yield f"event: {event.event_type}\ndata: {json.dumps(event.to_wire(), default=str)}\n\n"
                if event.event_type in terminal:
                    break
        finally:
            bus.unsubscribe(sub.id)

    return StreamingResponse(event_source(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------------------
# Datasets / Versions
# ---------------------------------------------------------------------------


def _dataset_dict(d: Dataset) -> dict:
    return {"id": d.id, "project_id": d.project_id, "name": d.name,
            "description": d.description, "current_version_id": d.current_version_id,
            "created_at": d.created_at}


@router.get("/datasets", tags=["datasets"])
def list_datasets(principal: Principal = Depends(get_principal),
                  project_id: str | None = None,
                  cursor: str | None = None, limit: int = Query(50, le=200)):
    with session_scope() as session:
        q = session.query(Dataset).filter_by(org_id=principal.org_id)
        if project_id:
            q = q.filter_by(project_id=project_id)
        q = q.order_by(Dataset.created_at.desc(), Dataset.id.desc())
        if cursor and (decoded := _decode_cursor(cursor)):
            q = q.filter(Dataset.created_at <= decoded[0], Dataset.id != decoded[1])
        rows = q.limit(limit + 1).all()
        return _paginate(rows, limit, _dataset_dict)


@router.get("/datasets/{dataset_id}", tags=["datasets"])
def get_dataset(dataset_id: str, principal: Principal = Depends(get_principal)):
    with session_scope() as session:
        d = session.get(Dataset, dataset_id)
        if d is None or d.org_id != principal.org_id:
            raise HTTPException(status_code=404, detail="dataset not found")
        versions = (session.query(DatasetVersion).filter_by(dataset_id=dataset_id)
                    .order_by(DatasetVersion.created_at.desc()).all())
        return {**_dataset_dict(d),
                "versions": [{"id": v.id, "version": v.version, "status": v.status,
                              "record_count": v.record_count, "content_hash": v.content_hash,
                              "created_at": v.created_at} for v in versions]}


@router.get("/datasets/{dataset_id}/versions/{version_id}", tags=["datasets"])
def get_dataset_version(dataset_id: str, version_id: str,
                        principal: Principal = Depends(get_principal),
                        sample: int = Query(10, le=100)):
    with session_scope() as session:
        v = session.get(DatasetVersion, version_id)
        if v is None or v.org_id != principal.org_id or v.dataset_id != dataset_id:
            raise HTTPException(status_code=404, detail="dataset version not found")
        chunks = (session.query(Chunk)
                  .filter_by(org_id=principal.org_id, run_id=v.pipeline_run_id, status="active")
                  .limit(sample).all())
        return {"id": v.id, "dataset_id": v.dataset_id, "version": v.version,
                "status": v.status, "manifest": v.manifest, "quality_report": v.quality_report,
                "dataset_card": v.dataset_card, "content_hash": v.content_hash,
                "record_count": v.record_count, "created_at": v.created_at,
                "sample_records": [{"id": c.id, "content": c.content[:800],
                                    "scores": c.scores} for c in chunks]}


@router.post("/datasets/{dataset_id}/publish", tags=["datasets"])
def publish_dataset(dataset_id: str, principal: Principal = Depends(require_role(Role.ADMIN))):
    """Publish the current version (approval gate: Admin+ only)."""
    with session_scope() as session:
        d = session.get(Dataset, dataset_id)
        if d is None or d.org_id != principal.org_id:
            raise HTTPException(status_code=404, detail="dataset not found")
        if not d.current_version_id:
            raise HTTPException(status_code=400, detail="dataset has no versions")
        v = session.get(DatasetVersion, d.current_version_id)
        gates = v.quality_report.get("gates", {})
        if gates and not all(gates.values()):
            failing = [k for k, ok in gates.items() if not ok]
            raise HTTPException(status_code=409,
                                detail=f"quality gates failing: {', '.join(failing)}")
        v.status = "published"
        version_id = v.id
    get_event_bus().emit("dataset.version.published", tenant_id=principal.org_id,
                         actor=f"user:{principal.user_id}",
                         payload={"resource_type": "dataset_version", "resource_id": version_id})
    return {"dataset_id": dataset_id, "version_id": version_id, "status": "published"}


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------


class ExportBody(BaseModel):
    dataset_version_id: str
    format: str = "jsonl"


@router.post("/exports", status_code=202, tags=["exports"])
def create_export_job(body: ExportBody, principal: Principal = Depends(require_role(Role.BUILDER))):
    with session_scope() as session:
        v = session.get(DatasetVersion, body.dataset_version_id)
        if v is None or v.org_id != principal.org_id:
            raise HTTPException(status_code=404, detail="dataset version not found")
    try:
        export_id = export_service.create_export(principal.org_id, body.dataset_version_id, body.format)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    get_task_queue().submit(f"export:{export_id}", export_service.execute_export, export_id)
    return {"export_id": export_id, "status": "queued"}


@router.get("/exports/{export_id}", tags=["exports"])
def get_export(export_id: str, principal: Principal = Depends(get_principal)):
    with session_scope() as session:
        job = session.get(ExportJob, export_id)
        if job is None or job.org_id != principal.org_id:
            raise HTTPException(status_code=404, detail="export not found")
        return {"id": job.id, "format": job.format, "status": job.status,
                "size_bytes": job.size_bytes, "checksum": job.checksum,
                "error": job.error, "created_at": job.created_at}


@router.get("/exports/{export_id}/download", tags=["exports"])
def download_export(export_id: str, principal: Principal = Depends(get_principal)):
    from backend.storage.object_store import get_object_store

    with session_scope() as session:
        job = session.get(ExportJob, export_id)
        if job is None or job.org_id != principal.org_id:
            raise HTTPException(status_code=404, detail="export not found")
        if job.status != "succeeded":
            raise HTTPException(status_code=409, detail=f"export status is '{job.status}'")
        key, fmt = job.storage_key, job.format
    data = get_object_store().get(key)
    ext = "zip" if fmt == "hf" else fmt
    return Response(content=data, media_type=export_service.mime_for(fmt),
                    headers={"Content-Disposition": f'attachment; filename="dataforge_{export_id}.{ext}"'})


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------


@router.get("/agents", tags=["agents"])
def list_agents(principal: Principal = Depends(get_principal)):
    return {"items": get_agent_registry().list()}


class InvokeBody(BaseModel):
    project_id: str = ""
    params: dict = Field(default_factory=dict)


@router.post("/agents/{agent_name}/invoke", status_code=202, tags=["agents"])
def invoke(agent_name: str, body: InvokeBody,
           principal: Principal = Depends(require_role(Role.BUILDER))):
    try:
        get_agent_registry().get(agent_name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown agent '{agent_name}'")
    ctx = AgentContext(org_id=principal.org_id, project_id=body.project_id,
                       actor=f"user:{principal.user_id}")
    try:
        return invoke_agent(agent_name, ctx, body.params)
    except PermissionError as exc:
        raise HTTPException(status_code=402, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/agent-runs", tags=["agents"])
def list_agent_runs(principal: Principal = Depends(get_principal),
                    project_id: str | None = None, status: str | None = None,
                    limit: int = Query(50, le=200)):
    with session_scope() as session:
        q = session.query(AgentRun).filter_by(org_id=principal.org_id)
        if project_id:
            q = q.filter_by(project_id=project_id)
        if status:
            q = q.filter_by(status=status)
        rows = q.order_by(AgentRun.started_at.desc()).limit(limit).all()
        return {"items": [{"id": r.id, "agent": r.agent_name, "status": r.status,
                           "project_id": r.project_id, "pipeline_run_id": r.pipeline_run_id,
                           "cost_usd": r.cost_usd, "started_at": r.started_at,
                           "finished_at": r.finished_at} for r in rows]}


@router.get("/agent-runs/{agent_run_id}", tags=["agents"])
def get_agent_run(agent_run_id: str, principal: Principal = Depends(get_principal)):
    with session_scope() as session:
        r = session.get(AgentRun, agent_run_id)
        if r is None or r.org_id != principal.org_id:
            raise HTTPException(status_code=404, detail="agent run not found")
        return {"id": r.id, "agent": r.agent_name, "status": r.status, "input": r.input,
                "output": r.output, "error": r.error, "cost_usd": r.cost_usd,
                "started_at": r.started_at, "finished_at": r.finished_at}


@router.post("/agent-runs/{agent_run_id}/approve", tags=["agents"])
def approve_run(agent_run_id: str, principal: Principal = Depends(require_role(Role.ADMIN))):
    try:
        return approve_agent_run(principal.org_id, agent_run_id, f"user:{principal.user_id}")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


class RejectBody(BaseModel):
    reason: str = ""


@router.post("/agent-runs/{agent_run_id}/reject", tags=["agents"])
def reject_run(agent_run_id: str, body: RejectBody,
               principal: Principal = Depends(require_role(Role.ADMIN))):
    try:
        return reject_agent_run(principal.org_id, agent_run_id,
                                f"user:{principal.user_id}", body.reason)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------


@router.get("/reviews", tags=["review"])
def list_reviews(principal: Principal = Depends(get_principal),
                 status: str = "pending", limit: int = Query(50, le=200)):
    with session_scope() as session:
        rows = (session.query(ReviewItem)
                .filter_by(org_id=principal.org_id, status=status)
                .order_by(ReviewItem.priority.desc(), ReviewItem.created_at.asc())
                .limit(limit).all())
        items = []
        for r in rows:
            subject_preview = ""
            if r.subject_type == "chunk":
                chunk = session.get(Chunk, r.subject_id)
                subject_preview = chunk.content[:400] if chunk else ""
            items.append({"id": r.id, "subject_type": r.subject_type,
                          "subject_id": r.subject_id, "reason": r.reason,
                          "priority": r.priority, "status": r.status,
                          "subject_preview": subject_preview, "created_at": r.created_at})
        return {"items": items}


class ReviewDecision(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    notes: str = ""


@router.post("/reviews/{review_id}", tags=["review"])
def decide_review(review_id: str, body: ReviewDecision,
                  principal: Principal = Depends(require_role(Role.REVIEWER))):
    try:
        return resolve_review(principal.org_id, review_id, principal.user_id,
                              body.decision, body.notes)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ---------------------------------------------------------------------------
# Knowledge graph
# ---------------------------------------------------------------------------


@router.get("/graph", tags=["graph"])
def get_graph(project_id: str, principal: Principal = Depends(get_principal),
              limit: int = Query(200, le=1000)):
    return graph_service.get_graph(principal.org_id, project_id, limit)


# ---------------------------------------------------------------------------
# Plugins
# ---------------------------------------------------------------------------


@router.get("/plugins/available", tags=["plugins"])
def available_plugins(principal: Principal = Depends(get_principal)):
    return {"items": plugin_service.discover_available()}


@router.get("/plugins", tags=["plugins"])
def installed_plugins(principal: Principal = Depends(get_principal)):
    return {"items": plugin_service.list_installed(principal.org_id)}


class PluginInstallBody(BaseModel):
    manifest: dict


@router.post("/plugins", status_code=201, tags=["plugins"])
def install_plugin(body: PluginInstallBody,
                   principal: Principal = Depends(require_role(Role.ADMIN))):
    try:
        plugin_id = plugin_service.install(principal.org_id, body.manifest)
    except plugin_service.PluginError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"id": plugin_id}


# ---------------------------------------------------------------------------
# Admin / observability
# ---------------------------------------------------------------------------


@router.get("/admin/health", tags=["admin"])
def health():
    from backend.intelligence.llm import get_llm_router

    return {"status": "ok", "llm_online": get_llm_router().online}


@router.get("/admin/metrics", tags=["admin"])
def metrics(principal: Principal = Depends(get_principal)):
    from backend.events.handlers import METRICS

    with session_scope() as session:
        counts = {
            "projects": session.query(Project).filter_by(org_id=principal.org_id).count(),
            "datasets": session.query(Dataset).filter_by(org_id=principal.org_id).count(),
            "documents": session.query(Document).filter_by(org_id=principal.org_id).count(),
            "records": session.query(Chunk).filter_by(org_id=principal.org_id).count(),
            "runs": session.query(PipelineRun).filter_by(org_id=principal.org_id).count(),
            "pending_reviews": session.query(ReviewItem).filter_by(
                org_id=principal.org_id, status="pending").count(),
        }
    return {"resources": counts, "events": dict(METRICS)}


@router.get("/admin/audit-logs", tags=["admin"])
def audit_logs(principal: Principal = Depends(require_role(Role.ADMIN)),
               limit: int = Query(100, le=500)):
    with session_scope() as session:
        rows = (session.query(AuditLog).filter_by(org_id=principal.org_id)
                .order_by(AuditLog.created_at.desc()).limit(limit).all())
        return {"items": [{"id": r.id, "actor": r.actor, "action": r.action,
                           "resource_type": r.resource_type, "resource_id": r.resource_id,
                           "created_at": r.created_at} for r in rows]}


@router.get("/admin/usage", tags=["admin"])
def usage(principal: Principal = Depends(get_principal)):
    from sqlalchemy import func

    with session_scope() as session:
        cost = (session.query(func.coalesce(func.sum(AgentRun.cost_usd), 0.0))
                .filter(AgentRun.org_id == principal.org_id).scalar())
        tokens = (session.query(func.coalesce(func.sum(AgentRun.tokens_used), 0))
                  .filter(AgentRun.org_id == principal.org_id).scalar())
        agent_runs = session.query(AgentRun).filter_by(org_id=principal.org_id).count()
    return {"llm_cost_usd": round(float(cost or 0), 4), "llm_tokens": int(tokens or 0),
            "agent_runs": agent_runs}


@router.get("/quality-reports", tags=["admin"])
def quality_reports(principal: Principal = Depends(get_principal),
                    run_id: str | None = None, limit: int = Query(20, le=100)):
    with session_scope() as session:
        q = session.query(QualityReport).filter_by(org_id=principal.org_id)
        if run_id:
            q = q.filter_by(run_id=run_id)
        rows = q.order_by(QualityReport.created_at.desc()).limit(limit).all()
        return {"items": [{"id": r.id, "run_id": r.run_id,
                           "dataset_version_id": r.dataset_version_id,
                           "scores": r.scores, "gates": r.gates,
                           "created_at": r.created_at} for r in rows]}
