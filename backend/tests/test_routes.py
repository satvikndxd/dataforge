"""Tests for the /api routes.

Network-dependent pipeline work (DuckDuckGo search) is stubbed via monkeypatch so
these tests are deterministic and offline.
"""
import pytest


FAKE_SOURCES = [
    {
        "title": "Climate Overview",
        "url": "https://example.com/climate",
        "domain": "example.com",
        "relevance_score": 1.0,
        "selected": True,
    }
]


@pytest.fixture
def stub_search(monkeypatch):
    """Replace the network search so /research's background task is offline."""
    from core import research
    monkeypatch.setattr(research, "search_topic", lambda *a, **k: list(FAKE_SOURCES))


# --- /research -------------------------------------------------------------

def test_research_creates_job(client, stub_search):
    resp = client.post("/api/research", json={"topic": "climate change", "modality": "text"})
    assert resp.status_code == 200
    body = resp.json()
    assert "job_id" in body and body["job_id"]


def test_research_runs_pipeline_to_source_selection(client, stub_search):
    job_id = client.post("/api/research", json={"topic": "climate change"}).json()["job_id"]
    # TestClient runs the BackgroundTask before returning, so status should advance.
    status = client.get(f"/api/status/{job_id}").json()
    assert status["status"] in {"searching", "pending_selection"}
    sources = client.get(f"/api/sources/{job_id}").json()["sources"]
    assert sources and sources[0]["url"] == FAKE_SOURCES[0]["url"]


@pytest.mark.parametrize(
    "payload",
    [
        {"topic": "x"},                                   # topic too short (min_length=2)
        {"topic": "valid topic", "modality": "bogus"},    # invalid modality literal
        {"topic": "valid topic", "num_sources": 5},       # below ge=10
        {"topic": "valid topic", "num_sources": 999},     # above le=50
        {"topic": "valid topic", "format": "xml"},        # invalid format literal
        {},                                               # missing required topic
    ],
)
def test_research_rejects_invalid_input(client, payload):
    resp = client.post("/api/research", json=payload)
    assert resp.status_code == 422


# --- /status, /sources, /results, /select_sources : 404 on unknown job -----

def test_status_unknown_job_404(client):
    assert client.get("/api/status/does-not-exist").status_code == 404


def test_sources_unknown_job_404(client):
    assert client.get("/api/sources/does-not-exist").status_code == 404


def test_results_unknown_job_404(client):
    assert client.get("/api/results/does-not-exist").status_code == 404


def test_select_sources_unknown_job_404(client):
    resp = client.post(
        "/api/select_sources",
        json={"job_id": "does-not-exist", "selected_urls": ["https://example.com"]},
    )
    assert resp.status_code == 404


def test_results_not_finished_returns_400(client, stub_search):
    """A freshly created job is not 'done', so /results must reject it."""
    job_id = client.post("/api/research", json={"topic": "climate change"}).json()["job_id"]
    resp = client.get(f"/api/results/{job_id}")
    assert resp.status_code == 400
