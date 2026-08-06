"""Export packaging (spec §6.4).

Formats: JSONL, JSON, CSV, Parquet (via polars when installed), SQLite,
Hugging Face-style bundle (data + README dataset card). Every export is
checksummed and stored in the object store.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
import tempfile
from datetime import datetime, timezone

from backend.core.ids import new_id
from backend.db.base import session_scope
from backend.db.models import Chunk, DatasetVersion, Document, ExportJob
from backend.events.bus import get_event_bus
from backend.storage.object_store import get_object_store

SUPPORTED_FORMATS = ["jsonl", "json", "csv", "parquet", "sqlite", "hf"]


def collect_records(org_id: str, dataset_version_id: str) -> list[dict]:
    """Materialize the version's records (active chunks with lineage)."""
    with session_scope() as session:
        version = session.get(DatasetVersion, dataset_version_id)
        if version is None or version.org_id != org_id:
            raise ValueError("dataset version not found")
        run_id = version.pipeline_run_id
        chunks = (
            session.query(Chunk)
            .filter(Chunk.org_id == org_id, Chunk.run_id == run_id, Chunk.status == "active")
            .order_by(Chunk.document_id, Chunk.position)
            .all()
        )
        doc_ids = {c.document_id for c in chunks}
        docs = {
            d.id: d
            for d in session.query(Document).filter(Document.id.in_(doc_ids)).all()
        } if doc_ids else {}

    records = []
    for chunk in chunks:
        doc = docs.get(chunk.document_id)
        records.append(
            {
                "record_id": chunk.id,
                "content": chunk.content,
                "source_url": doc.url if doc else "",
                "title": doc.title if doc else "",
                "language": doc.language if doc else "en",
                "license_hint": doc.license_hint if doc else "unknown",
                "quality_score": chunk.scores.get("total", None),
                "position": chunk.position,
                "document_id": chunk.document_id,
                "metadata": chunk.meta,
            }
        )
    return records


# ---------------------------------------------------------------------------
# Format writers
# ---------------------------------------------------------------------------


def _to_jsonl(records: list[dict]) -> bytes:
    return "\n".join(json.dumps(r, ensure_ascii=False, default=str) for r in records).encode()


def _to_json(records: list[dict]) -> bytes:
    return json.dumps({"records": records, "count": len(records)},
                      ensure_ascii=False, indent=2, default=str).encode()


def _to_csv(records: list[dict]) -> bytes:
    buf = io.StringIO()
    fields = ["record_id", "content", "source_url", "title", "language",
              "license_hint", "quality_score", "position", "document_id"]
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(records)
    return buf.getvalue().encode()


def _to_parquet(records: list[dict]) -> bytes:
    try:
        import polars as pl  # type: ignore

        flat = [{k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in r.items()}
                for r in records]
        df = pl.DataFrame(flat)
        buf = io.BytesIO()
        df.write_parquet(buf)
        return buf.getvalue()
    except ImportError:
        raise RuntimeError("parquet export requires polars: pip install polars")


def _to_sqlite(records: list[dict]) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        conn = sqlite3.connect(tmp.name)
        conn.execute(
            """CREATE TABLE records (
                record_id TEXT PRIMARY KEY, content TEXT, source_url TEXT, title TEXT,
                language TEXT, license_hint TEXT, quality_score REAL,
                position INTEGER, document_id TEXT, metadata TEXT
            )"""
        )
        conn.executemany(
            "INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,?)",
            [
                (r["record_id"], r["content"], r["source_url"], r["title"], r["language"],
                 r["license_hint"], r["quality_score"], r["position"], r["document_id"],
                 json.dumps(r["metadata"], default=str))
                for r in records
            ],
        )
        conn.commit()
        conn.close()
        tmp.seek(0)
        return tmp.read()


def _to_hf_bundle(records: list[dict], card: str) -> bytes:
    """Hugging Face-style bundle: zip with data/train.jsonl + README.md card."""
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("data/train.jsonl", _to_jsonl(records))
        zf.writestr("README.md", card or "# Dataset\n")
        zf.writestr("dataset_infos.json", json.dumps({"default": {"num_records": len(records)}}))
    return buf.getvalue()


_WRITERS = {
    "jsonl": lambda records, card: _to_jsonl(records),
    "json": lambda records, card: _to_json(records),
    "csv": lambda records, card: _to_csv(records),
    "parquet": lambda records, card: _to_parquet(records),
    "sqlite": lambda records, card: _to_sqlite(records),
    "hf": _to_hf_bundle,
}

_MIME = {
    "jsonl": "application/jsonl",
    "json": "application/json",
    "csv": "text/csv",
    "parquet": "application/vnd.apache.parquet",
    "sqlite": "application/vnd.sqlite3",
    "hf": "application/zip",
}


def mime_for(fmt: str) -> str:
    return _MIME.get(fmt, "application/octet-stream")


# ---------------------------------------------------------------------------
# Job lifecycle
# ---------------------------------------------------------------------------


def create_export(org_id: str, dataset_version_id: str, fmt: str) -> str:
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(f"unsupported format '{fmt}'; supported: {SUPPORTED_FORMATS}")
    export_id = new_id("exp")
    with session_scope() as session:
        session.add(ExportJob(id=export_id, org_id=org_id,
                              dataset_version_id=dataset_version_id, format=fmt))
    get_event_bus().emit("export.started", tenant_id=org_id,
                         payload={"export_id": export_id, "format": fmt,
                                  "resource_type": "export", "resource_id": export_id})
    return export_id


def execute_export(export_id: str) -> None:
    with session_scope() as session:
        job = session.get(ExportJob, export_id)
        if job is None:
            return
        org_id, version_id, fmt = job.org_id, job.dataset_version_id, job.format
        job.status = "running"

    try:
        with session_scope() as session:
            version = session.get(DatasetVersion, version_id)
            card = version.dataset_card if version else ""
        records = collect_records(org_id, version_id)
        data = _WRITERS[fmt](records, card)
        checksum = hashlib.sha256(data).hexdigest()
        ext = "zip" if fmt == "hf" else fmt
        key = f"orgs/{org_id}/exports/{export_id}.{ext}"
        get_object_store().put(key, data)
        with session_scope() as session:
            job = session.get(ExportJob, export_id)
            job.status = "succeeded"
            job.storage_key = key
            job.checksum = checksum
            job.size_bytes = len(data)
            job.finished_at = datetime.now(timezone.utc)
        get_event_bus().emit("export.completed", tenant_id=org_id,
                             payload={"export_id": export_id, "format": fmt,
                                      "size_bytes": len(data), "checksum": checksum,
                                      "resource_type": "export", "resource_id": export_id})
    except Exception as exc:
        with session_scope() as session:
            job = session.get(ExportJob, export_id)
            if job:
                job.status = "failed"
                job.error = str(exc)
                job.finished_at = datetime.now(timezone.utc)
        get_event_bus().emit("alert.raised", tenant_id=org_id,
                             payload={"kind": "export_failed", "export_id": export_id,
                                      "error": str(exc)})
