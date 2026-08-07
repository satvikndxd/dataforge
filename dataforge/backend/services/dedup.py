"""Multi-layer deduplication (spec §6.2 stage 9, §7.4).

Layers:
1. exact content hash (SHA-256 of normalized text)
2. URL canonicalization
3. near-duplicate MinHash / Jaccard over word shingles
4. semantic duplicate via embedding cosine (vector index)
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
                    "fbclid", "gclid", "ref", "mc_cid", "mc_eid"}

_WORD_RE = re.compile(r"[a-z0-9]+")


def normalize_text(text: str) -> str:
    return " ".join(_WORD_RE.findall(text.lower()))


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode()).hexdigest()


def canonical_url(url: str) -> str:
    try:
        p = urlparse(url.strip())
        query = urlencode(sorted((k, v) for k, v in parse_qsl(p.query) if k not in _TRACKING_PARAMS))
        netloc = p.netloc.lower().removeprefix("www.")
        path = p.path.rstrip("/") or "/"
        return urlunparse((p.scheme.lower() or "https", netloc, path, "", query, ""))
    except ValueError:
        return url


# ---------------------------------------------------------------------------
# MinHash
# ---------------------------------------------------------------------------

_NUM_PERM = 64
_MERSENNE = (1 << 61) - 1
# deterministic hash-function parameters
_AS = [(i * 2654435761 + 1) % _MERSENNE for i in range(1, _NUM_PERM + 1)]
_BS = [(i * 40503 + 7) % _MERSENNE for i in range(1, _NUM_PERM + 1)]


def _shingles(text: str, k: int = 3) -> set[int]:
    words = _WORD_RE.findall(text.lower())
    if len(words) < k:
        return {hash(" ".join(words)) & 0xFFFFFFFF} if words else set()
    return {
        int.from_bytes(hashlib.blake2b(" ".join(words[i:i + k]).encode(), digest_size=4).digest(), "big")
        for i in range(len(words) - k + 1)
    }


def minhash_signature(text: str) -> list[int]:
    sh = _shingles(text)
    if not sh:
        return [0] * _NUM_PERM
    return [min(((a * s + b) % _MERSENNE) & 0xFFFFFFFF for s in sh) for a, b in zip(_AS, _BS)]


def minhash_similarity(sig_a: list[int], sig_b: list[int]) -> float:
    if not sig_a or not sig_b or len(sig_a) != len(sig_b):
        return 0.0
    return sum(1 for a, b in zip(sig_a, sig_b) if a == b) / len(sig_a)


# ---------------------------------------------------------------------------
# Deduplicator
# ---------------------------------------------------------------------------


@dataclass
class DedupVerdict:
    is_duplicate: bool
    method: str = ""          # exact | url | near | semantic
    duplicate_of: str = ""    # id of canonical record
    similarity: float = 0.0


class Deduplicator:
    """Streaming dedup over a corpus; keeps fingerprint indices in memory."""

    def __init__(self, near_threshold: float = 0.85, semantic_threshold: float = 0.95):
        self.near_threshold = near_threshold
        self.semantic_threshold = semantic_threshold
        self._hashes: dict[str, str] = {}
        self._urls: dict[str, str] = {}
        self._signatures: dict[str, list[int]] = {}

    def check_and_add(self, record_id: str, text: str, url: str = "",
                      embedding: list[float] | None = None,
                      semantic_lookup=None) -> DedupVerdict:
        h = content_hash(text)
        if h in self._hashes:
            return DedupVerdict(True, "exact", self._hashes[h], 1.0)

        if url:
            cu = canonical_url(url)
            if cu in self._urls:
                return DedupVerdict(True, "url", self._urls[cu], 1.0)

        sig = minhash_signature(text)
        for other_id, other_sig in self._signatures.items():
            sim = minhash_similarity(sig, other_sig)
            if sim >= self.near_threshold:
                return DedupVerdict(True, "near", other_id, sim)

        if embedding is not None and semantic_lookup is not None:
            hits = semantic_lookup(embedding)
            for hit in hits:
                if hit.score >= self.semantic_threshold and hit.id != record_id:
                    return DedupVerdict(True, "semantic", hit.id, hit.score)

        # canonical record — index it
        self._hashes[h] = record_id
        if url:
            self._urls[canonical_url(url)] = record_id
        self._signatures[record_id] = sig
        return DedupVerdict(False)
