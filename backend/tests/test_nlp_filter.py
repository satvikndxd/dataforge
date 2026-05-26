"""Tests for the TF-IDF relevance scoring in core.nlp_filter."""
from core import nlp_filter


def test_empty_input_returns_empty():
    assert nlp_filter.score_paragraphs([], "any topic") == []


def test_relevant_paragraph_ranks_above_irrelevant():
    paragraphs = [
        ("u1", "climate change drives global warming and rising temperatures"),
        ("u2", "a simple recipe for homemade pasta with tomato sauce"),
    ]
    results = nlp_filter.score_paragraphs(paragraphs, "climate change", threshold=0.0)
    # Both kept at threshold 0.0, sorted by score descending.
    assert [r[0] for r in results][0] == "u1"
    # The on-topic paragraph scores strictly higher than the off-topic one.
    scores = {r[0]: r[2] for r in results}
    assert scores["u1"] > scores["u2"]


def test_threshold_filters_out_low_scores():
    paragraphs = [
        ("u1", "climate change and carbon emissions policy"),
        ("u2", "totally unrelated content about ancient roman architecture"),
    ]
    results = nlp_filter.score_paragraphs(paragraphs, "climate change", threshold=0.5)
    urls = [r[0] for r in results]
    assert "u2" not in urls  # below the 0.5 threshold


def test_results_are_sorted_descending():
    paragraphs = [
        ("u1", "barely related mention of weather"),
        ("u2", "climate change climate change global warming emissions"),
        ("u3", "climate change policy summary"),
    ]
    results = nlp_filter.score_paragraphs(paragraphs, "climate change", threshold=0.0)
    scores = [r[2] for r in results]
    assert scores == sorted(scores, reverse=True)
