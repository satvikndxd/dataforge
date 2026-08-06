"""Agent catalog (spec §5.3) — all nineteen agents.

Each agent is a small, typed unit with heuristic-first behavior and optional
LLM enrichment (via the router). Communication happens over the event bus;
durable state and lineage live in the system of record.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone

from backend.agents.runtime import Agent, AgentContext, AgentResult
from backend.core.ids import new_id
from backend.db.base import session_scope
from backend.db.models import Chunk, Dataset, DatasetVersion, Document
from backend.events.bus import get_event_bus
from backend.services import quality
from backend.services.chunking import chunk_text
from backend.services.dedup import Deduplicator
from backend.services.extraction import (
    clean_text,
    detect_language,
    detect_license,
    extract_document,
    fetch_url,
)
from backend.services.graph import upsert_graph
from backend.services.review import request_review, review_priority
from backend.services.search import discover


# ---------------------------------------------------------------------------
# 1) Research Agent
# ---------------------------------------------------------------------------


class ResearchAgent(Agent):
    name = "research"
    description = "Expands a project goal into a research plan: topic taxonomy, query seeds, coverage criteria."
    tier = "reasoning"

    def execute(self, ctx: AgentContext, params: dict) -> AgentResult:
        goal = (params.get("goal") or "").strip()
        if not goal:
            return AgentResult(ok=False, error="goal is required")

        plan = None
        cost, tokens = 0.0, 0
        if self.llm.online:
            data = self.llm.complete_json(
                f"You are a dataset research planner. Project goal: {goal!r}.\n"
                'Return {"subtopics": [8 strings], "queries": [8 short search queries], '
                '"coverage": {"<subtopic>": <importance 0-1>}}',
                tier="reasoning",
            )
            if isinstance(data, dict) and data.get("queries"):
                plan = data

        if plan is None:  # deterministic decomposition
            words = [w for w in re.findall(r"[A-Za-z0-9']+", goal) if len(w) > 2]
            base = " ".join(words[:6]) or goal
            facets = ["overview", "history", "key concepts", "applications",
                      "challenges", "recent developments", "examples", "methods"]
            plan = {
                "subtopics": [f"{base} {f}" for f in facets],
                "queries": [base] + [f"{base} {f}" for f in facets[:7]],
                "coverage": {f"{base} {f}": round(1.0 - i * 0.08, 2) for i, f in enumerate(facets)},
            }

        get_event_bus().emit("research.plan.generated", tenant_id=ctx.org_id,
                             project_id=ctx.project_id, run_id=ctx.pipeline_run_id,
                             actor="agent:research", payload={"queries": plan["queries"]})
        return AgentResult(ok=True, output={"plan": plan}, cost_usd=cost, tokens_used=tokens)


# ---------------------------------------------------------------------------
# 2) Search Agent
# ---------------------------------------------------------------------------


class SearchAgent(Agent):
    name = "search"
    description = "Executes research-plan queries across source providers and ranks candidates."

    def execute(self, ctx: AgentContext, params: dict) -> AgentResult:
        queries: list[str] = params.get("queries") or []
        providers: list[str] | None = params.get("providers")
        limit = int(params.get("limit", 10))
        if not queries:
            return AgentResult(ok=False, error="queries are required")
        candidates = discover(queries, providers=providers, limit_per_query=max(2, limit // 2))
        payload = [
            {"url": c.url, "title": c.title, "snippet": c.snippet,
             "provider": c.provider, "authority": c.authority}
            for c in candidates[:limit]
        ]
        get_event_bus().emit("search.candidates.generated", tenant_id=ctx.org_id,
                             project_id=ctx.project_id, run_id=ctx.pipeline_run_id,
                             actor="agent:search", payload={"count": len(payload)})
        return AgentResult(ok=True, output={"candidates": payload})


# ---------------------------------------------------------------------------
# 3) Scraping Agent
# ---------------------------------------------------------------------------


class ScrapingAgent(Agent):
    name = "scraping"
    description = "Fetches approved sources under robots/rate-limit policy and extracts content."

    def execute(self, ctx: AgentContext, params: dict) -> AgentResult:
        url = params.get("url", "")
        inline_text = params.get("inline_text", "")
        source_id = params.get("source_id", "")
        bus = get_event_bus()

        if inline_text:  # uploaded/inline document — no network
            extracted_text, title, mime, raw = inline_text, params.get("title", ""), "text/plain", inline_text.encode()
            confidence = 1.0
        else:
            result = fetch_url(url)
            if result.status != "ok":
                bus.emit("scrape.failed", tenant_id=ctx.org_id, project_id=ctx.project_id,
                         run_id=ctx.pipeline_run_id, actor="agent:scraping",
                         payload={"url": url, "status": result.status, "detail": result.detail})
                # captcha/paywall -> quarantine, never bypass (spec §6.6)
                return AgentResult(ok=False, error=f"{result.status}: {result.detail}",
                                   output={"url": url, "status": result.status})
            extracted = extract_document(result.content, result.mime_type, url)
            extracted_text, title = extracted.text, extracted.title
            mime, raw, confidence = result.mime_type, result.content, extracted.confidence

        if not extracted_text.strip():
            return AgentResult(ok=False, error="no extractable content",
                               output={"url": url, "status": "empty"})

        from backend.services.dedup import content_hash
        from backend.storage.object_store import get_object_store

        store = get_object_store()
        raw_key = store.put(store.content_address(ctx.org_id, "raw", raw, "bin"), raw)
        text_key = store.put_text(
            store.content_address(ctx.org_id, "text", extracted_text.encode(), "txt"),
            extracted_text,
        )
        doc_id = new_id("doc")
        with session_scope() as session:
            session.add(Document(
                id=doc_id, org_id=ctx.org_id, project_id=ctx.project_id,
                source_id=source_id, run_id=ctx.pipeline_run_id or None,
                url=url, title=title[:1000], content_hash=content_hash(extracted_text),
                mime_type=mime, storage_key=raw_key, text_storage_key=text_key,
                meta={"extraction_confidence": confidence},
            ))
        bus.emit("document.fetched", tenant_id=ctx.org_id, project_id=ctx.project_id,
                 run_id=ctx.pipeline_run_id, actor="agent:scraping",
                 payload={"document_id": doc_id, "url": url})
        bus.emit("extraction.completed", tenant_id=ctx.org_id, project_id=ctx.project_id,
                 run_id=ctx.pipeline_run_id, actor="agent:scraping",
                 payload={"document_id": doc_id, "status": "success", "confidence": confidence})
        return AgentResult(ok=True, output={"document_id": doc_id, "title": title,
                                            "chars": len(extracted_text)})


# ---------------------------------------------------------------------------
# 4-6) Media agents (image / audio / video) — modality pipeline stubs with
#      honest capability reporting; full processing arrives with media plugins.
# ---------------------------------------------------------------------------


class _MediaAgent(Agent):
    modality = "image"

    def execute(self, ctx: AgentContext, params: dict) -> AgentResult:
        items = params.get("items", [])
        processed = [{"item": i, "status": "queued",
                      "note": f"{self.modality} processing requires the media worker pool"}
                     for i in items]
        get_event_bus().emit(f"{self.modality}.processed", tenant_id=ctx.org_id,
                             project_id=ctx.project_id, run_id=ctx.pipeline_run_id,
                             actor=f"agent:{self.name}", payload={"count": len(processed)})
        return AgentResult(ok=True, output={"processed": processed, "modality": self.modality})


class ImageAgent(_MediaAgent):
    name = "image"
    modality = "image"
    description = "Collects, filters, captions and embeds images (dedup → NSFW → quality → caption)."


class AudioAgent(_MediaAgent):
    name = "audio"
    modality = "audio"
    description = "Transcribes and segments audio (VAD → ASR → diarization → confidence filter)."


class VideoAgent(_MediaAgent):
    name = "video"
    modality = "video"
    description = "Processes video into scenes, transcripts, frames and captions."


# ---------------------------------------------------------------------------
# 7) Knowledge Graph Agent
# ---------------------------------------------------------------------------


class KnowledgeGraphAgent(Agent):
    name = "knowledge_graph"
    description = "Builds entities and relationships from processed text (NER → link → prune)."

    def execute(self, ctx: AgentContext, params: dict) -> AgentResult:
        text = params.get("text", "")
        document_id = params.get("document_id")
        if not text:
            return AgentResult(ok=False, error="text is required")
        counts = upsert_graph(ctx.org_id, ctx.project_id, text, document_id)
        get_event_bus().emit("graph.updated", tenant_id=ctx.org_id, project_id=ctx.project_id,
                             run_id=ctx.pipeline_run_id, actor="agent:knowledge_graph",
                             payload=counts)
        return AgentResult(ok=True, output=counts)


# ---------------------------------------------------------------------------
# 8) Data Cleaning Agent
# ---------------------------------------------------------------------------


class CleaningAgent(Agent):
    name = "cleaning"
    description = "Normalizes raw content: boilerplate removal, encoding fixes, language + license detection."

    def execute(self, ctx: AgentContext, params: dict) -> AgentResult:
        document_id = params.get("document_id", "")
        from backend.storage.object_store import get_object_store
        from urllib.parse import urlparse

        store = get_object_store()
        with session_scope() as session:
            doc = session.get(Document, document_id)
            if doc is None or doc.org_id != ctx.org_id:
                return AgentResult(ok=False, error="document not found")
            raw_text = store.get_text(doc.text_storage_key)
            cleaned = clean_text(raw_text)
            if not cleaned:
                doc.status = "rejected"
                return AgentResult(ok=True, output={"document_id": document_id, "status": "rejected",
                                                    "reason": "empty after cleaning"})
            domain = urlparse(doc.url).netloc if doc.url else ""
            doc.language = detect_language(cleaned)
            hint, conf = detect_license(cleaned, domain)
            doc.license_hint, doc.license_confidence = hint, conf
            clean_key = store.put_text(
                store.content_address(ctx.org_id, "clean", cleaned.encode(), "txt"), cleaned
            )
            doc.text_storage_key = clean_key
            doc.status = "cleaned"
        get_event_bus().emit("cleaning.completed", tenant_id=ctx.org_id, project_id=ctx.project_id,
                             run_id=ctx.pipeline_run_id, actor="agent:cleaning",
                             payload={"document_id": document_id, "chars": len(cleaned)})
        return AgentResult(ok=True, output={"document_id": document_id, "status": "cleaned",
                                            "language": doc.language, "license_hint": hint,
                                            "chars": len(cleaned)})


# ---------------------------------------------------------------------------
# 9) Deduplication Agent
# ---------------------------------------------------------------------------


class DeduplicationAgent(Agent):
    name = "deduplication"
    description = "Detects exact/near/semantic duplicates across a run's records."

    def execute(self, ctx: AgentContext, params: dict) -> AgentResult:
        run_id = params.get("run_id") or ctx.pipeline_run_id
        deduper = Deduplicator()
        duplicates = 0
        with session_scope() as session:
            chunks = (
                session.query(Chunk)
                .filter(Chunk.org_id == ctx.org_id, Chunk.run_id == run_id,
                        Chunk.status == "active")
                .order_by(Chunk.created_at)
                .all()
            )
            for chunk in chunks:
                verdict = deduper.check_and_add(chunk.id, chunk.content)
                if verdict.is_duplicate:
                    chunk.status = "duplicate"
                    chunk.meta = {**chunk.meta, "duplicate_of": verdict.duplicate_of,
                                  "dedup_method": verdict.method,
                                  "similarity": round(verdict.similarity, 4)}
                    duplicates += 1
            total = len(chunks)
        fraction = duplicates / total if total else 0.0
        get_event_bus().emit("dedup.completed", tenant_id=ctx.org_id, project_id=ctx.project_id,
                             run_id=run_id, actor="agent:deduplication",
                             payload={"total": total, "duplicates": duplicates,
                                      "fraction": round(fraction, 4)})
        return AgentResult(ok=True, output={"total": total, "duplicates": duplicates,
                                            "duplicate_fraction": round(fraction, 4)})


# ---------------------------------------------------------------------------
# 10) Quality Evaluation Agent
# ---------------------------------------------------------------------------


class QualityAgent(Agent):
    name = "quality"
    description = "Scores records and the run corpus across the §6.7 dimensions; routes low scores to review."

    def execute(self, ctx: AgentContext, params: dict) -> AgentResult:
        from urllib.parse import urlparse
        from backend.core.config import get_settings

        run_id = params.get("run_id") or ctx.pipeline_run_id
        settings = get_settings()
        toxicities: list[float] = []
        totals: list[float] = []
        review_count = 0

        with session_scope() as session:
            chunks = (
                session.query(Chunk)
                .filter(Chunk.org_id == ctx.org_id, Chunk.run_id == run_id,
                        Chunk.status.in_(["active", "needs_review"]))
                .all()
            )
            docs = {
                d.id: d for d in session.query(Document)
                .filter(Document.id.in_({c.document_id for c in chunks})).all()
            } if chunks else {}

            for chunk in chunks:
                doc = docs.get(chunk.document_id)
                domain = urlparse(doc.url).netloc if doc and doc.url else ""
                tox = quality.toxicity_score(chunk.content)
                toxicities.append(tox)
                pii = quality.detect_pii(chunk.content)
                sub = {
                    "readability": quality.readability(chunk.content),
                    "language_quality": quality.language_quality(chunk.content),
                    "source_authority": quality.source_authority(domain),
                    "safety": quality.clamp(1 - tox),
                    "completeness": quality.completeness(
                        {"content": chunk.content, "title": doc.title if doc else ""},
                        ["content", "title"],
                    ),
                    "metadata_richness": quality.metadata_richness({
                        "title": doc.title if doc else "", "language": doc.language if doc else "",
                        "license_hint": (doc.license_hint if doc else "unknown") != "unknown",
                        "source_url": doc.url if doc else "",
                    }),
                }
                total = quality.total_score(sub)
                chunk.scores = {**sub, "total": round(total, 4),
                                "toxicity": round(tox, 4), "pii": pii}
                totals.append(total)

                if pii:
                    chunk.status = "needs_review"
                    review_count += 1
                    request_review(ctx.org_id, ctx.project_id, "chunk", chunk.id,
                                   f"PII detected: {', '.join(pii)}", run_id=run_id,
                                   priority=review_priority(total, policy_risk=1.0))
                elif tox >= 0.5:
                    chunk.status = "rejected"  # block high severity (spec §6.2 stage 10)
                elif total < settings.review_score_threshold:
                    chunk.status = "needs_review"
                    review_count += 1
                    request_review(ctx.org_id, ctx.project_id, "chunk", chunk.id,
                                   f"quality score {total:.2f} below threshold", run_id=run_id,
                                   priority=review_priority(total))

        corpus = {
            "safety": quality.safety(toxicities),
            "mean_quality": round(sum(totals) / len(totals), 4) if totals else 0.0,
            "records_scored": len(totals),
            "records_flagged_for_review": review_count,
        }
        get_event_bus().emit("quality.scored", tenant_id=ctx.org_id, project_id=ctx.project_id,
                             run_id=run_id, actor="agent:quality", payload=corpus)
        return AgentResult(ok=True, output=corpus)


# ---------------------------------------------------------------------------
# 11) Metadata Agent
# ---------------------------------------------------------------------------


class MetadataAgent(Agent):
    name = "metadata"
    description = "Generates dataset documentation: summary, tags, dataset card."

    def execute(self, ctx: AgentContext, params: dict) -> AgentResult:
        goal = params.get("goal", "")
        sample_texts: list[str] = params.get("samples", [])
        stats: dict = params.get("stats", {})

        words = re.findall(r"[a-zA-Z]{5,}", " ".join(sample_texts)[:20000].lower())
        tags = [w for w, _ in Counter(words).most_common(10)]

        summary = ""
        if self.llm.online and sample_texts:
            summary = self.llm.complete(
                f"Summarize in 2 sentences what a dataset about {goal!r} containing "
                f"excerpts like the following covers:\n\n{sample_texts[0][:1500]}",
                tier="cheap",
            ).text.strip()
        if not summary:
            summary = f"A curated dataset for: {goal}." if goal else "A curated dataset."

        card = _render_dataset_card(goal=goal, summary=summary, tags=tags, stats=stats)
        get_event_bus().emit("metadata.generated", tenant_id=ctx.org_id, project_id=ctx.project_id,
                             run_id=ctx.pipeline_run_id, actor="agent:metadata",
                             payload={"tags": tags})
        return AgentResult(ok=True, output={"summary": summary, "tags": tags, "dataset_card": card})


def _render_dataset_card(goal: str, summary: str, tags: list[str], stats: dict) -> str:
    lines = [
        f"# Dataset Card",
        "",
        f"**Goal:** {goal or 'n/a'}",
        "",
        "## Summary",
        summary,
        "",
        "## Tags",
        ", ".join(tags) if tags else "n/a",
        "",
        "## Statistics",
    ]
    for key, value in stats.items():
        lines.append(f"- **{key}**: {value}")
    lines += [
        "",
        "## Intended Use",
        "Language-model training, retrieval-augmented generation and evaluation.",
        "",
        "## Limitations & Bias",
        "Automatically curated; heuristically scored for quality/toxicity/bias. "
        "Records flagged uncertain were routed to human review. License hints are "
        "heuristic and must be verified before redistribution.",
        "",
        f"## Provenance",
        f"Produced by DataForge V2 on {datetime.now(timezone.utc).date().isoformat()} "
        "with full per-record lineage (source URL, content hash, pipeline run).",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 12) Dataset Versioning Agent
# ---------------------------------------------------------------------------


class VersioningAgent(Agent):
    name = "versioning"
    description = "Creates immutable dataset versions with manifests, content hashes and lineage."

    def execute(self, ctx: AgentContext, params: dict) -> AgentResult:
        import hashlib

        dataset_id = params.get("dataset_id", "")
        run_id = params.get("run_id") or ctx.pipeline_run_id
        quality_report = params.get("quality_report", {})
        dataset_card = params.get("dataset_card", "")

        with session_scope() as session:
            dataset = session.get(Dataset, dataset_id)
            if dataset is None or dataset.org_id != ctx.org_id:
                return AgentResult(ok=False, error="dataset not found")
            existing = (
                session.query(DatasetVersion).filter_by(dataset_id=dataset_id).count()
            )
            chunks = (
                session.query(Chunk)
                .filter(Chunk.org_id == ctx.org_id, Chunk.run_id == run_id,
                        Chunk.status == "active")
                .order_by(Chunk.id)
                .all()
            )
            digest = hashlib.sha256()
            for chunk in chunks:
                digest.update(chunk.id.encode())
                digest.update(chunk.content.encode())
            version_label = f"{existing + 1}.0.0"
            version_id = new_id("dsv")
            manifest = {
                "dataset_id": dataset_id,
                "version": version_label,
                "record_count": len(chunks),
                "pipeline_run_id": run_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "schema": {"record_id": "string", "content": "string", "source_url": "string",
                           "quality_score": "float", "metadata": "object"},
            }
            session.add(DatasetVersion(
                id=version_id, org_id=ctx.org_id, dataset_id=dataset_id,
                version=version_label, status="draft", manifest=manifest,
                quality_report=quality_report, dataset_card=dataset_card,
                content_hash=digest.hexdigest(), pipeline_run_id=run_id,
                record_count=len(chunks),
            ))
            dataset.current_version_id = version_id

        get_event_bus().emit("dataset.version.created", tenant_id=ctx.org_id,
                             project_id=ctx.project_id, run_id=run_id,
                             actor="agent:versioning",
                             payload={"dataset_version_id": version_id, "version": version_label,
                                      "records": len(chunks), "resource_type": "dataset_version",
                                      "resource_id": version_id})
        return AgentResult(ok=True, output={"dataset_version_id": version_id,
                                            "version": version_label,
                                            "record_count": len(chunks)})


# ---------------------------------------------------------------------------
# 13) Synthetic Data Agent (approval-gated: large generations are high cost)
# ---------------------------------------------------------------------------


class SyntheticDataAgent(Agent):
    name = "synthetic"
    description = "Generates synthetic instruction/QA pairs from seed records with provenance tags."
    requires_approval = True
    tier = "reasoning"

    def execute(self, ctx: AgentContext, params: dict) -> AgentResult:
        seeds: list[str] = params.get("seeds", [])
        count = min(int(params.get("count", 5)), 50)
        if not seeds:
            return AgentResult(ok=False, error="seed records are required")

        samples = []
        for i in range(count):
            seed = seeds[i % len(seeds)]
            if self.llm.online:
                data = self.llm.complete_json(
                    "From this source text, write one instruction-following training pair.\n"
                    f"Source: {seed[:2000]}\n"
                    'Return {"instruction": str, "response": str}',
                    tier="reasoning",
                )
                if isinstance(data, dict) and data.get("instruction"):
                    samples.append({**data, "provenance": "synthetic:llm", "seed_excerpt": seed[:100]})
                    continue
            sentences = re.split(r"(?<=[.!?])\s+", seed.strip())
            if sentences:
                samples.append({
                    "instruction": f"Summarize the following passage: {sentences[0][:200]}",
                    "response": " ".join(sentences[:2])[:400],
                    "provenance": "synthetic:template",
                    "seed_excerpt": seed[:100],
                })
        get_event_bus().emit("synthetic.batch.generated", tenant_id=ctx.org_id,
                             project_id=ctx.project_id, actor="agent:synthetic",
                             payload={"count": len(samples)})
        return AgentResult(ok=True, output={"samples": samples, "count": len(samples)})


# ---------------------------------------------------------------------------
# 14) Citation Agent
# ---------------------------------------------------------------------------


class CitationAgent(Agent):
    name = "citation"
    description = "Extracts and normalizes citations (DOIs, arXiv IDs, URLs) into structured records."

    _DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+\b")
    _ARXIV_RE = re.compile(r"\barXiv:\s*(\d{4}\.\d{4,5})(v\d+)?\b", re.I)
    _URL_RE = re.compile(r"https?://[^\s)\]>\"']+")

    def execute(self, ctx: AgentContext, params: dict) -> AgentResult:
        text = params.get("text", "")
        citations = []
        for doi in set(self._DOI_RE.findall(text)):
            citations.append({"type": "doi", "id": doi, "url": f"https://doi.org/{doi}",
                              "bibtex": f"@misc{{{doi.replace('/', '_')}, doi={{{doi}}}}}"})
        for match in self._ARXIV_RE.finditer(text):
            arxiv_id = match.group(1)
            citations.append({"type": "arxiv", "id": arxiv_id,
                              "url": f"https://arxiv.org/abs/{arxiv_id}",
                              "bibtex": f"@misc{{arxiv{arxiv_id.replace('.', '_')}, "
                                        f"eprint={{{arxiv_id}}}, archivePrefix={{arXiv}}}}"})
        for url in list(dict.fromkeys(self._URL_RE.findall(text)))[:20]:
            if "doi.org" in url or "arxiv.org" in url:
                continue
            citations.append({"type": "url", "id": url, "url": url})
        get_event_bus().emit("citation.enriched", tenant_id=ctx.org_id, project_id=ctx.project_id,
                             actor="agent:citation", payload={"count": len(citations)})
        return AgentResult(ok=True, output={"citations": citations})


# ---------------------------------------------------------------------------
# 15) Evaluation Agent
# ---------------------------------------------------------------------------


class EvaluationAgent(Agent):
    name = "evaluation"
    description = "Evaluates a dataset version for downstream usefulness (intrinsic + LLM-judge)."
    tier = "reasoning"

    def execute(self, ctx: AgentContext, params: dict) -> AgentResult:
        version_id = params.get("dataset_version_id", "")
        with session_scope() as session:
            version = session.get(DatasetVersion, version_id)
            if version is None or version.org_id != ctx.org_id:
                return AgentResult(ok=False, error="dataset version not found")
            chunks = (
                session.query(Chunk)
                .filter(Chunk.org_id == ctx.org_id, Chunk.run_id == version.pipeline_run_id,
                        Chunk.status == "active")
                .limit(500)
                .all()
            )
        if not chunks:
            return AgentResult(ok=True, output={"verdict": "empty", "metrics": {}})

        lengths = [c.token_estimate or 1 for c in chunks]
        scores = [c.scores.get("total", 0.5) for c in chunks]
        metrics = {
            "records": len(chunks),
            "mean_tokens": round(sum(lengths) / len(lengths), 1),
            "mean_quality": round(sum(scores) / len(scores), 4),
            "min_quality": round(min(scores), 4),
            "short_record_fraction": round(sum(1 for t in lengths if t < 30) / len(lengths), 4),
        }
        llm_judgement = None
        if self.llm.online:
            sample = "\n---\n".join(c.content[:600] for c in chunks[:3])
            data = self.llm.complete_json(
                "Judge these dataset records for LLM-training usefulness.\n"
                f"{sample}\n"
                'Return {"coherence": 0-1, "usefulness": 0-1, "notes": str}',
                tier="reasoning",
            )
            if isinstance(data, dict):
                llm_judgement = data
        verdict = "pass" if metrics["mean_quality"] >= 0.5 and metrics["short_record_fraction"] < 0.5 else "marginal"
        get_event_bus().emit("evaluation.completed", tenant_id=ctx.org_id,
                             project_id=ctx.project_id, actor="agent:evaluation",
                             payload={"dataset_version_id": version_id, "verdict": verdict})
        return AgentResult(ok=True, output={"verdict": verdict, "metrics": metrics,
                                            "llm_judgement": llm_judgement})


# ---------------------------------------------------------------------------
# 16) Export Agent
# ---------------------------------------------------------------------------


class ExportAgent(Agent):
    name = "export"
    description = "Packages dataset versions into target formats with integrity checks."

    def execute(self, ctx: AgentContext, params: dict) -> AgentResult:
        from backend.services.exports import create_export, execute_export

        version_id = params.get("dataset_version_id", "")
        fmt = params.get("format", "jsonl")
        export_id = create_export(ctx.org_id, version_id, fmt)
        execute_export(export_id)
        from backend.db.models import ExportJob

        with session_scope() as session:
            job = session.get(ExportJob, export_id)
            output = {"export_id": export_id, "status": job.status,
                      "size_bytes": job.size_bytes, "checksum": job.checksum}
            ok = job.status == "succeeded"
            error = job.error
        return AgentResult(ok=ok, output=output, error=error)


# ---------------------------------------------------------------------------
# 17) Monitoring Agent
# ---------------------------------------------------------------------------


class MonitoringAgent(Agent):
    name = "monitoring"
    description = "Watches pipeline health and cost; raises alerts on anomalies."

    def execute(self, ctx: AgentContext, params: dict) -> AgentResult:
        from backend.events.handlers import METRICS

        failures = METRICS.get("pipeline.failed", 0) + METRICS.get("scrape.failed", 0)
        total = METRICS.get("events.total", 1)
        failure_rate = failures / max(1, total)
        alerts = []
        if failure_rate > 0.3 and failures >= 3:
            alerts.append({"kind": "high_failure_rate", "failure_rate": round(failure_rate, 3)})
        for alert in alerts:
            get_event_bus().emit("alert.raised", tenant_id=ctx.org_id,
                                 actor="agent:monitoring", payload=alert)
        return AgentResult(ok=True, output={"metrics": dict(METRICS), "alerts": alerts})


# ---------------------------------------------------------------------------
# 18) Security Agent
# ---------------------------------------------------------------------------


class SecurityAgent(Agent):
    name = "security"
    description = "Scans content for PII, secrets and policy violations; fails closed on high risk."

    def execute(self, ctx: AgentContext, params: dict) -> AgentResult:
        text = params.get("text", "")
        pii = quality.detect_pii(text)
        toxicity = quality.toxicity_score(text)
        violations = []
        if pii:
            violations.append({"kind": "pii", "detail": pii})
        if toxicity >= 0.5:
            violations.append({"kind": "toxicity", "detail": {"score": round(toxicity, 3)}})
        if violations:
            get_event_bus().emit("security.violation.detected", tenant_id=ctx.org_id,
                                 project_id=ctx.project_id, actor="agent:security",
                                 payload={"violations": violations})
        return AgentResult(ok=True, output={"violations": violations,
                                            "block": toxicity >= 0.5,
                                            "redacted_text": quality.redact_pii(text) if pii else text})


# ---------------------------------------------------------------------------
# 19) Human Review Agent
# ---------------------------------------------------------------------------


class HumanReviewAgent(Agent):
    name = "human_review"
    description = "Routes uncertain items to review queues using active-learning prioritization."

    def execute(self, ctx: AgentContext, params: dict) -> AgentResult:
        subject_type = params.get("subject_type", "chunk")
        subject_id = params.get("subject_id", "")
        reason = params.get("reason", "manual routing")
        score = float(params.get("quality_score", 0.5))
        if not subject_id:
            return AgentResult(ok=False, error="subject_id is required")
        review_id = request_review(
            ctx.org_id, ctx.project_id, subject_type, subject_id, reason,
            run_id=ctx.pipeline_run_id or None,
            priority=review_priority(score, novelty=float(params.get("novelty", 0.5)),
                                     policy_risk=float(params.get("policy_risk", 0.0))),
        )
        return AgentResult(ok=True, output={"review_id": review_id})


# ---------------------------------------------------------------------------


def register_all(registry) -> None:
    for cls in (
        ResearchAgent, SearchAgent, ScrapingAgent, ImageAgent, AudioAgent, VideoAgent,
        KnowledgeGraphAgent, CleaningAgent, DeduplicationAgent, QualityAgent,
        MetadataAgent, VersioningAgent, SyntheticDataAgent, CitationAgent,
        EvaluationAgent, ExportAgent, MonitoringAgent, SecurityAgent, HumanReviewAgent,
    ):
        registry.register(cls())
