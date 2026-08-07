"""Unit tests for the §6.7 quality scoring formulas."""
from datetime import datetime, timedelta, timezone

import pytest

from backend.services import quality as q


def test_completeness():
    assert q.completeness({"a": 1, "b": 2}, ["a", "b"]) == 1.0
    assert q.completeness({"a": 1, "b": None}, ["a", "b"]) == 0.5
    assert q.completeness({}, []) == 1.0


def test_freshness_decay():
    now = datetime.now(timezone.utc)
    assert q.freshness(now) > 0.99
    old = q.freshness(now - timedelta(days=365), tau_days=365)
    assert 0.3 < old < 0.4  # e^-1 ≈ 0.368
    assert q.freshness(None) == 0.5


def test_uniqueness():
    assert q.uniqueness(0, 100) == 1.0
    assert q.uniqueness(25, 100) == 0.75
    assert q.uniqueness(5, 0) == 1.0


def test_readability_bounds():
    simple = "The cat sat on the mat. The dog ran fast. It was a fun day."
    gnarly = "Notwithstanding heterogeneous institutional epistemologies, " * 10
    assert 0.0 <= q.readability(simple) <= 1.0
    assert q.readability(simple) > q.readability(gnarly)
    assert q.readability("") == 0.0


def test_source_authority_ranks_trusted_domains():
    assert q.source_authority("en.wikipedia.org") > q.source_authority("random-blog.biz")
    assert q.source_authority("arxiv.org") > 0.5
    verified = q.source_authority("example.com", publisher_verified=True)
    assert verified > q.source_authority("example.com")


def test_citation_quality():
    perfect = [{"relevance": 1.0, "venue_quality": 1.0}]
    poor = [{"relevance": 0.1, "venue_quality": 0.1}]
    assert q.citation_quality(perfect) == 1.0
    assert q.citation_quality(poor) < 0.1
    assert q.citation_quality([]) == 0.5


def test_language_quality_prefers_prose():
    prose = ("DataForge builds datasets from raw sources. It cleans and scores content. "
             "Human reviewers can inspect every record before publishing a version.")
    garbage = "asdf asdf asdf asdf asdf asdf asdf asdf ~~ ## @@ %% ^^ && **"
    assert q.language_quality(prose) > q.language_quality(garbage)
    assert q.language_quality("") == 0.0


def test_metadata_richness():
    full = {"title": "t", "summary": "s", "tags": ["a"], "language": "en",
            "license_hint": "mit", "source_url": "u", "entities": ["e"], "published_at": "d"}
    assert q.metadata_richness(full) == 1.0
    assert q.metadata_richness({}) == 0.0


def test_bias_risk():
    assert q.bias_risk({"a": 0.5, "b": 0.5}) == 0.0
    skewed = q.bias_risk({"a": 0.9, "b": 0.05, "c": 0.05})
    assert skewed > 0.5
    assert q.bias_risk({"a": 1.0}) == 0.0


def test_toxicity_and_safety():
    assert q.toxicity_score("A friendly article about gardening.") == 0.0
    assert q.toxicity_score("they should exterminate them all") >= 0.5
    assert q.safety([0.0, 0.0]) == 1.0
    assert q.safety([1.0, 0.0]) == 0.5


def test_coverage():
    taxonomy = {"intro": 1.0, "methods": 0.5, "results": 0.5}
    assert q.coverage(taxonomy, {"intro", "methods", "results"}) == 1.0
    assert q.coverage(taxonomy, {"intro"}) == 0.5
    assert q.coverage({}, set()) == 1.0


def test_representativeness():
    assert q.representativeness([0.5, 0.5], [0.5, 0.5]) == 1.0
    divergent = q.representativeness([1.0, 0.0], [0.0, 1.0])
    assert divergent < 0.1


def test_total_score_weighted():
    subs = {k: 1.0 for k in q.DEFAULT_WEIGHTS}
    assert q.total_score(subs) == 1.0
    subs["safety"] = 0.0
    assert q.total_score(subs) < 1.0


def test_gates():
    gates = q.evaluate_gates({"safety": 0.9}, {"duplicate_fraction": 0.1,
                                               "license_confidence": 0.8})
    assert all(v["passed"] for v in gates.values())
    gates = q.evaluate_gates({"safety": 0.5}, {"duplicate_fraction": 0.5,
                                               "license_confidence": 0.2,
                                               "pii_detected": True})
    assert not any(v["passed"] for v in gates.values())


def test_pii_detection():
    text = "Contact john.doe@example.com or 555-867-5309. SSN 123-45-6789. Card 4111 1111 1111 1111."
    findings = q.detect_pii(text)
    assert "email" in findings and "ssn" in findings and "credit_card" in findings
    redacted = q.redact_pii(text)
    assert "john.doe@example.com" not in redacted
    assert q.detect_pii("perfectly clean text") == {}
