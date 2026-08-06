"""Dataset quality scoring (spec §6.7).

Q_total = Σ w_i · s_i with normalized sub-scores. All formulas implemented
exactly as specified; each sub-score is clamped to [0, 1]. Deterministic
heuristics compute the base scores; LLM rubric scoring can refine
`language_quality`/`readability` when a provider is configured.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from datetime import datetime, timezone

DEFAULT_WEIGHTS: dict[str, float] = {
    "completeness": 0.10,
    "freshness": 0.05,
    "uniqueness": 0.15,
    "readability": 0.10,
    "source_authority": 0.10,
    "language_quality": 0.15,
    "metadata_richness": 0.05,
    "safety": 0.15,
    "coverage": 0.10,
    "bias_risk_inverse": 0.05,
}

_TRUSTED_TLDS = {"edu": 0.9, "gov": 0.95, "org": 0.7}
_TRUSTED_DOMAINS = {
    "wikipedia.org": 0.92, "arxiv.org": 0.95, "nature.com": 0.95, "acm.org": 0.9,
    "ieee.org": 0.9, "nih.gov": 0.95, "github.com": 0.75, "stackoverflow.com": 0.7,
    "britannica.com": 0.85, "reuters.com": 0.85, "apnews.com": 0.85,
}

_TOXIC_TERMS = {
    "kill yourself", "gas the", "subhuman", "exterminate them", "lynch",
    "white power", "heil", "rape her", "rape him", "child porn",
}

_WORD_RE = re.compile(r"[A-Za-z']+")
_SENT_RE = re.compile(r"(?<=[.!?])\s+")
_VOWELS = "aeiouy"


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


# ---------------------------------------------------------------------------
# Sub-scores
# ---------------------------------------------------------------------------


def completeness(record: dict, required_fields: list[str]) -> float:
    """1 - missing_required / total_required."""
    if not required_fields:
        return 1.0
    missing = sum(1 for f in required_fields if not record.get(f))
    return clamp(1 - missing / len(required_fields))


def freshness(updated_at: datetime | None, tau_days: float = 365.0) -> float:
    """e^(-max(0, now-updated_at)/τ)."""
    if updated_at is None:
        return 0.5
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (datetime.now(timezone.utc) - updated_at).total_seconds() / 86400)
    return clamp(math.exp(-age_days / tau_days))


def uniqueness(duplicate_records: int, total_records: int) -> float:
    """1 - duplicates/total."""
    if total_records <= 0:
        return 1.0
    return clamp(1 - duplicate_records / total_records)


def _count_syllables(word: str) -> int:
    word = word.lower()
    groups = re.findall(rf"[{_VOWELS}]+", word)
    n = len(groups)
    if word.endswith("e") and n > 1:
        n -= 1
    return max(1, n)


def flesch_reading_ease(text: str) -> float:
    words = _WORD_RE.findall(text)
    sentences = [s for s in _SENT_RE.split(text) if s.strip()]
    if not words or not sentences:
        return 0.0
    syllables = sum(_count_syllables(w) for w in words)
    asl = len(words) / len(sentences)
    asw = syllables / len(words)
    return 206.835 - 1.015 * asl - 84.6 * asw


def readability(text: str, fre_min: float = -30.0, fre_max: float = 100.0) -> float:
    """Normalized Flesch Reading Ease: (FRE - min) / (max - min)."""
    if not text.strip():
        return 0.0
    fre = flesch_reading_ease(text)
    return clamp((fre - fre_min) / (fre_max - fre_min))


def source_authority(domain: str, *, citation_score: float = 0.0,
                     publisher_verified: bool = False,
                     alpha: float = 0.6, beta: float = 0.25, gamma: float = 0.15) -> float:
    """α·DomainTrust + β·CitationScore + γ·PublisherVerification."""
    domain = (domain or "").lower().lstrip("www.")
    trust = 0.4
    for known, score in _TRUSTED_DOMAINS.items():
        if domain.endswith(known):
            trust = score
            break
    else:
        tld = domain.rsplit(".", 1)[-1] if "." in domain else ""
        trust = max(trust, _TRUSTED_TLDS.get(tld, trust))
    return clamp(alpha * trust + beta * clamp(citation_score) + gamma * (1.0 if publisher_verified else 0.0))


def citation_quality(citations: list[dict]) -> float:
    """(1/N)·Σ relevance_j · venue_quality_j."""
    if not citations:
        return 0.5
    total = sum(clamp(c.get("relevance", 0.5)) * clamp(c.get("venue_quality", 0.5)) for c in citations)
    return clamp(total / len(citations))


def language_quality(text: str) -> float:
    """Perplexity-proxy + grammar heuristics, normalized to [0,1].

    Offline proxy: character-entropy sanity, word-repetition penalty,
    non-alpha noise penalty, sentence-structure sanity.
    """
    if not text.strip():
        return 0.0
    words = _WORD_RE.findall(text.lower())
    if len(words) < 3:
        return 0.3

    # repetition penalty (mode frequency)
    counts = Counter(words)
    top_frac = counts.most_common(1)[0][1] / len(words)
    repetition = clamp(1 - max(0.0, top_frac - 0.1) * 3)

    # noise penalty: proportion of non-alphanumeric, non-space chars
    noise_chars = sum(1 for c in text if not (c.isalnum() or c.isspace() or c in ".,;:!?'\"()-—%$"))
    noise = clamp(1 - (noise_chars / max(1, len(text))) * 8)

    # structure: average sentence length in a sane band (5–40 words)
    sentences = [s for s in _SENT_RE.split(text) if s.strip()]
    asl = len(words) / max(1, len(sentences))
    structure = clamp(1 - abs(asl - 20) / 45)

    # lexical diversity
    diversity = clamp(len(counts) / len(words) * 2)

    return clamp(0.3 * repetition + 0.25 * noise + 0.25 * structure + 0.2 * diversity)


def metadata_richness(meta: dict, weighted_fields: dict[str, float] | None = None) -> float:
    """Σ present_weights / Σ total_weights."""
    weighted_fields = weighted_fields or {
        "title": 2.0, "summary": 1.5, "tags": 1.0, "language": 0.5,
        "license_hint": 1.5, "source_url": 1.0, "entities": 1.0, "published_at": 0.5,
    }
    total = sum(weighted_fields.values())
    present = sum(w for f, w in weighted_fields.items() if meta.get(f))
    return clamp(present / total if total else 1.0)


def bias_risk(group_proportions: dict[str, float]) -> float:
    """max(0, 1 - min_g(p_g)/E[p_g]). 0 = balanced, →1 = heavily skewed."""
    props = [p for p in group_proportions.values() if p >= 0]
    if len(props) < 2:
        return 0.0
    expected = sum(props) / len(props)
    if expected <= 0:
        return 0.0
    return clamp(1 - min(props) / expected)


def toxicity_score(text: str) -> float:
    """Per-record toxicity in [0,1] via term heuristics (classifier-swappable)."""
    lower = text.lower()
    hits = sum(1 for term in _TOXIC_TERMS if term in lower)
    # mild profanity contributes weakly
    mild = len(re.findall(r"\b(fuck|shit|bitch|asshole)\b", lower))
    return clamp(hits * 0.5 + mild * 0.05)


def safety(toxicities: list[float]) -> float:
    """1 - mean(toxicity)."""
    if not toxicities:
        return 1.0
    return clamp(1 - sum(toxicities) / len(toxicities))


def coverage(taxonomy: dict[str, float], covered_topics: set[str]) -> float:
    """Σ importance_t·covered_t / Σ importance_t."""
    if not taxonomy:
        return 1.0
    total = sum(taxonomy.values())
    got = sum(imp for topic, imp in taxonomy.items() if topic in covered_topics)
    return clamp(got / total if total else 1.0)


def representativeness(p_dataset: list[float], p_target: list[float]) -> float:
    """1 - JSD(P_dataset || P_target), JSD in bits (base 2) so ∈ [0,1]."""

    def _norm(p: list[float]) -> list[float]:
        s = sum(p)
        return [x / s for x in p] if s > 0 else [1.0 / len(p)] * len(p)

    if not p_dataset or not p_target or len(p_dataset) != len(p_target):
        return 0.5
    p, q = _norm(p_dataset), _norm(p_target)
    m = [(a + b) / 2 for a, b in zip(p, q)]

    def _kl(a: list[float], b: list[float]) -> float:
        return sum(x * math.log2(x / y) for x, y in zip(a, b) if x > 0 and y > 0)

    jsd = 0.5 * _kl(p, m) + 0.5 * _kl(q, m)
    return clamp(1 - jsd)


# ---------------------------------------------------------------------------
# Aggregation and gates
# ---------------------------------------------------------------------------


def total_score(sub_scores: dict[str, float], weights: dict[str, float] | None = None) -> float:
    weights = weights or DEFAULT_WEIGHTS
    applicable = {k: w for k, w in weights.items() if k in sub_scores}
    denom = sum(applicable.values()) or 1.0
    return clamp(sum(sub_scores[k] * w for k, w in applicable.items()) / denom)


def evaluate_gates(sub_scores: dict[str, float], stats: dict, settings=None) -> dict[str, dict]:
    """Quality gates (spec §6.7): dict of gate -> {passed, value, threshold}."""
    from backend.core.config import get_settings

    settings = settings or get_settings()
    duplicate_fraction = stats.get("duplicate_fraction", 0.0)
    gates = {
        "safety_min": {
            "passed": sub_scores.get("safety", 1.0) >= settings.gate_min_safety,
            "value": sub_scores.get("safety", 1.0),
            "threshold": settings.gate_min_safety,
            "action_on_fail": "reject",
        },
        "duplicate_fraction_max": {
            "passed": duplicate_fraction <= settings.gate_max_duplicate_fraction,
            "value": duplicate_fraction,
            "threshold": settings.gate_max_duplicate_fraction,
            "action_on_fail": "quarantine",
        },
        "license_confidence_min": {
            "passed": stats.get("license_confidence", 1.0) >= settings.gate_min_license_confidence,
            "value": stats.get("license_confidence", 1.0),
            "threshold": settings.gate_min_license_confidence,
            "action_on_fail": "require_review",
        },
        "pii_block": {
            "passed": not stats.get("pii_detected", False),
            "value": stats.get("pii_detected", False),
            "threshold": False,
            "action_on_fail": "block_publish",
        },
    }
    return gates


# ---------------------------------------------------------------------------
# PII detection (Security Agent primitive)
# ---------------------------------------------------------------------------

_PII_PATTERNS = {
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
    "phone": re.compile(r"\b(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}\b"),
    "aws_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"),
}


def detect_pii(text: str) -> dict[str, int]:
    findings: dict[str, int] = {}
    for kind, pattern in _PII_PATTERNS.items():
        matches = pattern.findall(text)
        if kind == "credit_card":
            matches = [m for m in matches if _luhn_ok(re.sub(r"\D", "", m))]
        if matches:
            findings[kind] = len(matches)
    return findings


def _luhn_ok(number: str) -> bool:
    if not 13 <= len(number) <= 16:
        return False
    total, alt = 0, False
    for d in reversed(number):
        n = int(d)
        if alt:
            n *= 2
            if n > 9:
                n -= 9
        total += n
        alt = not alt
    return total % 10 == 0


def redact_pii(text: str) -> str:
    for kind, pattern in _PII_PATTERNS.items():
        if kind == "phone":
            continue  # too many false positives to redact silently
        text = pattern.sub(f"[REDACTED:{kind.upper()}]", text)
    return text
