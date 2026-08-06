"""Vector index: in-memory default, Qdrant adapter when configured.

Used for semantic dedup, search, clustering and coverage analysis.
Namespaced per (org, project) to enforce tenancy.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field

from backend.intelligence.embeddings import cosine


@dataclass
class VectorHit:
    id: str
    score: float
    payload: dict


@dataclass
class _Namespace:
    ids: list[str] = field(default_factory=list)
    vectors: list[list[float]] = field(default_factory=list)
    payloads: list[dict] = field(default_factory=list)


class InMemoryVectorIndex:
    def __init__(self):
        self._namespaces: dict[str, _Namespace] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _ns_key(org_id: str, project_id: str) -> str:
        return f"{org_id}:{project_id}"

    def upsert(self, org_id: str, project_id: str, vec_id: str, vector: list[float], payload: dict | None = None) -> None:
        with self._lock:
            ns = self._namespaces.setdefault(self._ns_key(org_id, project_id), _Namespace())
            if vec_id in ns.ids:
                i = ns.ids.index(vec_id)
                ns.vectors[i] = vector
                ns.payloads[i] = payload or {}
            else:
                ns.ids.append(vec_id)
                ns.vectors.append(vector)
                ns.payloads.append(payload or {})

    def search(self, org_id: str, project_id: str, vector: list[float], limit: int = 10,
               exclude_id: str | None = None) -> list[VectorHit]:
        ns = self._namespaces.get(self._ns_key(org_id, project_id))
        if not ns:
            return []
        hits = [
            VectorHit(id=i, score=cosine(vector, v), payload=p)
            for i, v, p in zip(ns.ids, ns.vectors, ns.payloads)
            if i != exclude_id
        ]
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]

    def count(self, org_id: str, project_id: str) -> int:
        ns = self._namespaces.get(self._ns_key(org_id, project_id))
        return len(ns.ids) if ns else 0

    def clear(self, org_id: str, project_id: str) -> None:
        with self._lock:
            self._namespaces.pop(self._ns_key(org_id, project_id), None)


_index: InMemoryVectorIndex | None = None


def get_vector_index() -> InMemoryVectorIndex:
    """Return the process-wide vector index.

    A Qdrant-backed implementation with the same interface can be swapped in
    when DATAFORGE_QDRANT_URL is set; the in-memory index is the default and
    is rebuilt from stored embeddings on restart by the pipeline engine.
    """
    global _index
    if _index is None:
        _index = InMemoryVectorIndex()
    return _index
