"""Pipeline engine (spec §6).

A pipeline run is a checkpointed state machine over the stage DAG:

    discover → fetch → extract(+clean) → chunk → embed → dedup → score
    → graphify → document → version → publish?

Each stage records status/detail on the run row and emits
pipeline.stage.started / pipeline.stage.completed events, so the UI can
render a live DAG and failed runs can be diagnosed stage-by-stage. Stages
delegate the actual work to governed agents (spec §5) so every action is
audited and budgeted.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from backend.agents.runtime import AgentContext, invoke_agent
from backend.core.config import get_settings
from backend.core.ids import new_id
from backend.db.base import session_scope
from backend.db.models import Chunk, Dataset, DatasetVersion, Document, PipelineRun, QualityReport, Source
from backend.events.bus import get_event_bus
from backend.intelligence.embeddings import embed_text
from backend.intelligence.vector_index import get_vector_index
from backend.services.chunking import chunk_text
from backend.storage.object_store import get_object_store
from backend.workers.queue import get_task_queue

logger = logging.getLogger(__name__)

STAGES = ["discover", "fetch", "extract", "chunk", "embed", "dedup",
          "score", "graphify", "document", "version", "publish"]


# ---------------------------------------------------------------------------
# Run lifecycle
# ---------------------------------------------------------------------------


def create_run(org_id: str, project_id: str, *, dataset_id: str | None = None,
               config: dict | None = None, actor: str = "system") -> str:
    run_id = new_id("run")
    with session_scope() as session:
        session.add(PipelineRun(
            id=run_id, org_id=org_id, project_id=project_id, dataset_id=dataset_id,
            status="queued", config=config or {},
            stages=[{"name": s, "status": "pending", "detail": {}} for s in STAGES],
        ))
    get_event_bus().emit("pipeline.started", tenant_id=org_id, project_id=project_id,
                         run_id=run_id, actor=actor,
                         payload={"resource_type": "pipeline_run", "resource_id": run_id})
    return run_id


def start_run_async(run_id: str) -> None:
    get_task_queue().submit(f"pipeline:{run_id}", execute_run, run_id)


def cancel_run(org_id: str, run_id: str) -> bool:
    with session_scope() as session:
        run = session.get(PipelineRun, run_id)
        if run is None or run.org_id != org_id:
            raise ValueError("run not found")
        if run.status in ("succeeded", "failed", "cancelled"):
            return False
        run.status = "cancelled"
        run.finished_at = datetime.now(timezone.utc)
    return True


def _run_snapshot(run_id: str) -> PipelineRun | None:
    with session_scope() as session:
        return session.get(PipelineRun, run_id)


def _set_stage(run_id: str, stage: str, status: str, detail: dict | None = None) -> None:
    with session_scope() as session:
        run = session.get(PipelineRun, run_id)
        if run is None:
            return
        # deep-copy entries so SQLAlchemy's JSON change detection sees a new value
        stages = [dict(entry) for entry in run.stages]
        for entry in stages:
            if entry["name"] == stage:
                entry["status"] = status
                if detail:
                    entry["detail"] = detail
                entry[f"{status}_at"] = datetime.now(timezone.utc).isoformat()
        run.stages = stages
        if status == "running":
            run.current_stage = stage
        org_id, project_id = run.org_id, run.project_id
    event = "pipeline.stage.started" if status == "running" else "pipeline.stage.completed"
    get_event_bus().emit(event, tenant_id=org_id, project_id=project_id, run_id=run_id,
                         payload={"stage": stage, "status": status, **(detail or {})})


def _is_cancelled(run_id: str) -> bool:
    run = _run_snapshot(run_id)
    return run is not None and run.status == "cancelled"


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def execute_run(run_id: str) -> None:
    run = _run_snapshot(run_id)
    if run is None or run.status == "cancelled":
        return
    org_id, project_id, config = run.org_id, run.project_id, dict(run.config)
    dataset_id = run.dataset_id
    ctx = AgentContext(org_id=org_id, project_id=project_id, pipeline_run_id=run_id)

    with session_scope() as session:
        row = session.get(PipelineRun, run_id)
        row.status = "running"
        row.started_at = datetime.now(timezone.utc)

    stats: dict = {}
    try:
        # ---- 1. discover --------------------------------------------------
        _set_stage(run_id, "discover", "running")
        goal = config.get("goal", "")
        max_sources = int(config.get("max_sources", 5))
        candidates: list[dict] = []
        with session_scope() as session:
            sources = session.query(Source).filter_by(
                org_id=org_id, project_id=project_id, status="active").all()
            explicit = [
                {"url": s.uri, "source_id": s.id, "type": s.type,
                 "inline_text": s.config.get("text", ""), "title": s.config.get("title", "")}
                for s in sources if s.type in ("url", "inline", "file")
            ]
        candidates.extend(explicit)

        if config.get("auto_discover", True) and goal and len(candidates) < max_sources:
            plan_result = invoke_agent("research", ctx, {"goal": goal})
            queries = plan_result["output"].get("plan", {}).get("queries", [])[:4]
            stats["research_queries"] = queries
            if queries:
                search_result = invoke_agent("search", ctx, {
                    "queries": queries,
                    "providers": config.get("providers"),
                    "limit": max_sources - len(candidates),
                })
                discovered_id = _ensure_discovered_source(org_id, project_id)
                for cand in search_result["output"].get("candidates", []):
                    candidates.append({"url": cand["url"], "source_id": discovered_id,
                                       "type": "url", "inline_text": "", "title": cand["title"]})
        candidates = candidates[:max_sources]
        _set_stage(run_id, "discover", "succeeded", {"candidates": len(candidates)})
        stats["candidates"] = len(candidates)
        if _is_cancelled(run_id):
            return

        # ---- 2-3. fetch + extract (scraping agent handles both) ----------
        _set_stage(run_id, "fetch", "running")
        fetched = failed = 0
        for cand in candidates:
            try:
                result = invoke_agent("scraping", ctx, {
                    "url": cand.get("url", ""),
                    "inline_text": cand.get("inline_text", ""),
                    "title": cand.get("title", ""),
                    "source_id": cand.get("source_id", ""),
                })
                fetched += 1 if result["status"] == "succeeded" else 0
                failed += 0 if result["status"] == "succeeded" else 1
            except Exception as exc:
                logger.warning("fetch failed for %s: %s", cand.get("url"), exc)
                failed += 1
        _set_stage(run_id, "fetch", "succeeded", {"fetched": fetched, "failed": failed})
        stats.update({"documents_fetched": fetched, "fetch_failures": failed})
        if fetched == 0:
            raise RuntimeError("no documents could be fetched from any source")

        _set_stage(run_id, "extract", "running")
        cleaned = 0
        with session_scope() as session:
            doc_ids = [d.id for d in session.query(Document)
                       .filter_by(org_id=org_id, run_id=run_id).all()]
        for doc_id in doc_ids:
            result = invoke_agent("cleaning", ctx, {"document_id": doc_id})
            if result["output"].get("status") == "cleaned":
                cleaned += 1
        _set_stage(run_id, "extract", "succeeded", {"cleaned": cleaned})
        if _is_cancelled(run_id):
            return

        # ---- 4. chunk ------------------------------------------------------
        _set_stage(run_id, "chunk", "running")
        store = get_object_store()
        total_chunks = 0
        with session_scope() as session:
            docs = session.query(Document).filter_by(
                org_id=org_id, run_id=run_id, status="cleaned").all()
            for doc in docs:
                text = store.get_text(doc.text_storage_key)
                for tc in chunk_text(text, target_tokens=int(config.get("chunk_tokens", 400))):
                    session.add(Chunk(
                        id=new_id("chk"), org_id=org_id, document_id=doc.id,
                        run_id=run_id, position=tc.position, content=tc.content,
                        token_estimate=tc.token_estimate, meta=tc.meta,
                    ))
                    total_chunks += 1
        _set_stage(run_id, "chunk", "succeeded", {"chunks": total_chunks})
        stats["chunks"] = total_chunks

        # ---- 5. embed -------------------------------------------------------
        _set_stage(run_id, "embed", "running")
        index = get_vector_index()
        with session_scope() as session:
            chunks = session.query(Chunk).filter_by(org_id=org_id, run_id=run_id).all()
            for chunk in chunks:
                vector = embed_text(chunk.content)
                index.upsert(org_id, project_id, chunk.id, vector,
                             {"document_id": chunk.document_id})
                chunk.embedding_id = chunk.id
        get_event_bus().emit("embedding.generated", tenant_id=org_id, project_id=project_id,
                             run_id=run_id, payload={"count": total_chunks})
        _set_stage(run_id, "embed", "succeeded", {"embedded": total_chunks})
        if _is_cancelled(run_id):
            return

        # ---- 6. dedup --------------------------------------------------------
        _set_stage(run_id, "dedup", "running")
        dedup = invoke_agent("deduplication", ctx, {"run_id": run_id})
        _set_stage(run_id, "dedup", "succeeded", dedup["output"])
        stats["duplicate_fraction"] = dedup["output"].get("duplicate_fraction", 0.0)

        # ---- 7. score ----------------------------------------------------------
        _set_stage(run_id, "score", "running")
        scored = invoke_agent("quality", ctx, {"run_id": run_id})
        _set_stage(run_id, "score", "succeeded", scored["output"])
        stats.update(scored["output"])

        # ---- 8. graphify --------------------------------------------------------
        _set_stage(run_id, "graphify", "running")
        graph_totals = {"entities": 0, "relations": 0}
        if config.get("build_graph", True):
            with session_scope() as session:
                docs = session.query(Document).filter_by(
                    org_id=org_id, run_id=run_id, status="cleaned").limit(20).all()
                doc_payload = [(d.id, d.text_storage_key) for d in docs]
            for doc_id, key in doc_payload:
                text = store.get_text(key)
                result = invoke_agent("knowledge_graph", ctx,
                                      {"text": text[:50_000], "document_id": doc_id})
                graph_totals["entities"] += result["output"].get("entities", 0)
                graph_totals["relations"] += result["output"].get("relations", 0)
        _set_stage(run_id, "graphify", "succeeded", graph_totals)
        stats["graph"] = graph_totals

        # ---- 9. document (metadata + card) --------------------------------------
        _set_stage(run_id, "document", "running")
        with session_scope() as session:
            sample_chunks = (
                session.query(Chunk)
                .filter_by(org_id=org_id, run_id=run_id, status="active")
                .limit(3).all()
            )
            samples = [c.content for c in sample_chunks]
        meta_result = invoke_agent("metadata", ctx, {
            "goal": goal, "samples": samples,
            "stats": {"records": stats.get("records_scored", total_chunks),
                      "documents": fetched,
                      "duplicate_fraction": stats.get("duplicate_fraction", 0.0),
                      "mean_quality": stats.get("mean_quality", 0.0)},
        })
        dataset_card = meta_result["output"].get("dataset_card", "")
        _set_stage(run_id, "document", "succeeded",
                   {"tags": meta_result["output"].get("tags", [])})

        # ---- corpus-level quality report + gates ---------------------------------
        from backend.services import quality as q

        sub_scores = {
            "safety": stats.get("safety", 1.0),
            "uniqueness": q.uniqueness(
                int(stats.get("duplicate_fraction", 0.0) * max(1, total_chunks)), max(1, total_chunks)),
            "coverage": 1.0,
        }
        gates = q.evaluate_gates(sub_scores, {
            "duplicate_fraction": stats.get("duplicate_fraction", 0.0),
            "license_confidence": 0.7,
        })
        quality_report = {"scores": {**sub_scores, "mean_record_quality": stats.get("mean_quality", 0.0)},
                          "gates": {k: v["passed"] for k, v in gates.items()},
                          "stats": {k: v for k, v in stats.items() if not isinstance(v, (list, dict))}}
        with session_scope() as session:
            session.add(QualityReport(id=new_id("qr"), org_id=org_id, run_id=run_id,
                                      scores=quality_report["scores"], gates=gates,
                                      details={"stats": quality_report["stats"]}))

        # ---- 10. version -----------------------------------------------------------
        _set_stage(run_id, "version", "running")
        if dataset_id is None:
            dataset_id = _ensure_dataset(org_id, project_id, config.get("dataset_name") or goal or "dataset")
            with session_scope() as session:
                row = session.get(PipelineRun, run_id)
                row.dataset_id = dataset_id
        version_result = invoke_agent("versioning", ctx, {
            "dataset_id": dataset_id, "run_id": run_id,
            "quality_report": quality_report, "dataset_card": dataset_card,
        })
        version_id = version_result["output"].get("dataset_version_id")
        _set_stage(run_id, "version", "succeeded", version_result["output"])

        # link the quality report to the version
        with session_scope() as session:
            report = session.query(QualityReport).filter_by(run_id=run_id).first()
            if report and version_id:
                report.dataset_version_id = version_id

        # ---- 11. publish (gated) ----------------------------------------------------
        _set_stage(run_id, "publish", "running")
        gates_pass = all(v["passed"] for v in gates.values())
        auto_publish = bool(config.get("auto_publish", False))
        with session_scope() as session:
            version = session.get(DatasetVersion, version_id) if version_id else None
            if version is not None:
                if gates_pass and auto_publish:
                    version.status = "published"
                    publish_state = "published"
                else:
                    version.status = "pending_approval"
                    publish_state = "pending_approval"
            else:
                publish_state = "skipped"
        if publish_state == "pending_approval" and version_id:
            from backend.services.review import request_review

            reason = ("quality gates passed; awaiting human approval" if gates_pass
                      else "quality gates failed: " + ", ".join(k for k, v in gates.items() if not v["passed"]))
            request_review(org_id, project_id, "dataset_version", version_id, reason,
                           run_id=run_id, priority=0.9)
        if publish_state == "published":
            get_event_bus().emit("dataset.version.published", tenant_id=org_id,
                                 project_id=project_id, run_id=run_id,
                                 payload={"resource_type": "dataset_version",
                                          "resource_id": version_id})
        _set_stage(run_id, "publish", "succeeded", {"state": publish_state,
                                                    "gates_passed": gates_pass})

        with session_scope() as session:
            row = session.get(PipelineRun, run_id)
            row.status = "succeeded"
            row.stats = {k: v for k, v in stats.items() if not isinstance(v, list)}
            row.finished_at = datetime.now(timezone.utc)
        get_event_bus().emit("pipeline.completed", tenant_id=org_id, project_id=project_id,
                             run_id=run_id,
                             payload={"dataset_version_id": version_id, "stats": row.stats})

    except Exception as exc:
        logger.exception("pipeline run %s failed", run_id)
        with session_scope() as session:
            row = session.get(PipelineRun, run_id)
            if row is not None and row.status != "cancelled":
                row.status = "failed"
                row.error = str(exc)
                row.finished_at = datetime.now(timezone.utc)
                stages = [dict(entry) for entry in row.stages]
                for entry in stages:
                    if entry["status"] == "running":
                        entry["status"] = "failed"
                        entry["detail"] = {"error": str(exc)}
                row.stages = stages
        get_event_bus().emit("pipeline.failed", tenant_id=org_id, project_id=project_id,
                             run_id=run_id, payload={"error": str(exc)})


# ---------------------------------------------------------------------------


def _ensure_dataset(org_id: str, project_id: str, name: str) -> str:
    with session_scope() as session:
        existing = session.query(Dataset).filter_by(
            org_id=org_id, project_id=project_id, name=name[:255]).one_or_none()
        if existing:
            return existing.id
        dataset_id = new_id("ds")
        session.add(Dataset(id=dataset_id, org_id=org_id, project_id=project_id,
                            name=name[:255]))
    get_event_bus().emit("dataset.created", tenant_id=org_id, project_id=project_id,
                         payload={"resource_type": "dataset", "resource_id": dataset_id})
    return dataset_id


def _ensure_discovered_source(org_id: str, project_id: str) -> str:
    with session_scope() as session:
        existing = session.query(Source).filter_by(
            org_id=org_id, project_id=project_id, type="discovered").one_or_none()
        if existing:
            return existing.id
        source_id = new_id("src")
        session.add(Source(id=source_id, org_id=org_id, project_id=project_id,
                           type="discovered", uri="agent://search",
                           config={"note": "candidates discovered by the search agent"}))
        return source_id
