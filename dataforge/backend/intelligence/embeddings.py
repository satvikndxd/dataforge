"""Embedding generation.

Default: deterministic hashed n-gram embeddings (offline, zero deps).
They are good enough for dedup clustering, coverage analysis and
approximate semantic search in self-hosted deployments; production
deployments can switch to `sentence-transformers` when installed.
"""
from __future__ import annotations

import hashlib
import math
import re

from backend.core.config import get_settings

_TOKEN_RE = re.compile(r"[a-z0-9]+")

try:  # optional heavy dependency
    from sentence_transformers import SentenceTransformer  # type: ignore

    _st_model: "SentenceTransformer | None" = None

    def _load_st():  # pragma: no cover - heavyweight
        global _st_model
        if _st_model is None:
            _st_model = SentenceTransformer("all-MiniLM-L6-v2")
        return _st_model

    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:  # pragma: no cover
    HAS_SENTENCE_TRANSFORMERS = False


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def embed_text(text: str, dim: int | None = None) -> list[float]:
    """Return a unit-normalized embedding vector."""
    if HAS_SENTENCE_TRANSFORMERS:  # pragma: no cover
        return [float(x) for x in _load_st().encode(text[:4096])]

    dim = dim or get_settings().embedding_dim
    vec = [0.0] * dim
    toks = _tokens(text)
    grams = toks + [" ".join(p) for p in zip(toks, toks[1:])]
    for gram in grams:
        h = hashlib.blake2b(gram.encode(), digest_size=8).digest()
        idx = int.from_bytes(h[:4], "big") % dim
        sign = 1.0 if h[4] & 1 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))
