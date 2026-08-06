"""End-to-end integration: register → project → inline source → pipeline run
→ dataset version → export → review → agent governance."""
from __future__ import annotations

import time

SAMPLE_TEXT = """
# Nordic Runology

Runes are the letters in a set of related alphabets known as runic alphabets.
The Elder Futhark is the oldest form of the runic alphabets and was used by
Germanic peoples from the 2nd to the 8th centuries. Each rune carried both a
phonetic value and a symbolic meaning tied to Norse cosmology.

## The Younger Futhark

The Younger Futhark, also called Scandinavian runes, is a reduced form of the
Elder Futhark with only 16 characters. It appeared around the 9th century and
was the main alphabet in Scandinavia during the Viking Age. Inscriptions in
Younger Futhark are found on runestones throughout Sweden, Denmark and Norway.

## Rune Stones

Runestones are raised stones with runic inscriptions. Most were raised during
the 11th century as memorials to deceased relatives. The tradition of raising
runestones provides valuable historical evidence about Viking society, travel,
and the transition from Norse paganism to Christianity in Scandinavia.
""" * 2


def test_full_dataset_flow(client, auth):
    headers = auth["headers"]

    # 1. project
    resp = client.post("/v1/projects", headers=headers, json={
        "name": "Runology Corpus", "goal": "Nordic runology reference dataset",
    })
    assert resp.status_code == 201, resp.text
    project_id = resp.json()["id"]

    # 2. inline source (no network needed)
    resp = client.post("/v1/sources", headers=headers, json={
        "project_id": project_id, "type": "inline",
        "config": {"text": SAMPLE_TEXT, "title": "Nordic Runology Primer"},
    })
    assert resp.status_code == 201, resp.text

    # 3. run pipeline (no auto-discovery -> fully offline)
    resp = client.post("/v1/pipelines/run", headers=headers, json={
        "project_id": project_id, "dataset_name": "runology-v1",
        "auto_discover": False, "auto_publish": False,
    })
    assert resp.status_code == 202, resp.text
    run_id = resp.json()["run_id"]

    # 4. poll to completion
    for _ in range(120):
        run = client.get(f"/v1/runs/{run_id}", headers=headers).json()
        if run["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.25)
    assert run["status"] == "succeeded", run.get("error") or run
    stage_status = {s["name"]: s["status"] for s in run["stages"]}
    assert stage_status["fetch"] == "succeeded"
    assert stage_status["dedup"] == "succeeded"
    assert stage_status["version"] == "succeeded"
    assert run["stats"]["chunks"] > 0

    # 5. durable event trail exists
    events = client.get(f"/v1/runs/{run_id}/events", headers=headers).json()["items"]
    types = {e["event_type"] for e in events}
    assert {"pipeline.started", "document.fetched", "dedup.completed",
            "quality.scored", "dataset.version.created"} <= types

    # 6. dataset + version + card
    datasets = client.get("/v1/datasets", headers=headers,
                          params={"project_id": project_id}).json()["items"]
    assert len(datasets) == 1
    dataset = client.get(f"/v1/datasets/{datasets[0]['id']}", headers=headers).json()
    assert dataset["versions"], "expected at least one version"
    version = dataset["versions"][0]
    detail = client.get(
        f"/v1/datasets/{dataset['id']}/versions/{version['id']}", headers=headers
    ).json()
    assert detail["record_count"] > 0
    assert "# Dataset Card" in detail["dataset_card"]
    assert detail["manifest"]["pipeline_run_id"] == run_id
    assert detail["sample_records"]

    # 7. export -> download JSONL
    resp = client.post("/v1/exports", headers=headers,
                       json={"dataset_version_id": version["id"], "format": "jsonl"})
    assert resp.status_code == 202
    export_id = resp.json()["export_id"]
    for _ in range(60):
        job = client.get(f"/v1/exports/{export_id}", headers=headers).json()
        if job["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.2)
    assert job["status"] == "succeeded", job
    download = client.get(f"/v1/exports/{export_id}/download", headers=headers)
    assert download.status_code == 200
    first_line = download.text.splitlines()[0]
    assert '"content"' in first_line and '"source_url"' in first_line

    # 8. csv + hf bundle also work
    for fmt in ("csv", "hf"):
        resp = client.post("/v1/exports", headers=headers,
                           json={"dataset_version_id": version["id"], "format": fmt})
        assert resp.status_code == 202

    # 9. publish gate: version awaits approval, review item exists
    reviews = client.get("/v1/reviews", headers=headers).json()["items"]
    version_reviews = [r for r in reviews if r["subject_type"] == "dataset_version"]
    assert version_reviews, "expected a publish-approval review"
    decision = client.post(f"/v1/reviews/{version_reviews[0]['id']}", headers=headers,
                           json={"decision": "approved"})
    assert decision.status_code == 200
    detail = client.get(
        f"/v1/datasets/{dataset['id']}/versions/{version['id']}", headers=headers
    ).json()
    assert detail["status"] == "published"

    # 10. knowledge graph got built
    graph = client.get("/v1/graph", headers=headers,
                       params={"project_id": project_id}).json()
    assert len(graph["nodes"]) > 0


def test_agent_registry_and_governance(client, auth):
    headers = auth["headers"]
    agents = client.get("/v1/agents", headers=headers).json()["items"]
    names = {a["name"] for a in agents}
    assert len(names) == 19
    assert {"research", "search", "scraping", "cleaning", "deduplication", "quality",
            "metadata", "versioning", "synthetic", "citation", "evaluation", "export",
            "monitoring", "security", "human_review", "knowledge_graph",
            "image", "audio", "video"} <= names

    # synthetic agent requires approval -> parks in pending_approval
    resp = client.post("/v1/agents/synthetic/invoke", headers=headers, json={
        "params": {"seeds": ["The Elder Futhark has 24 runes."], "count": 2},
    })
    assert resp.status_code == 202, resp.text
    parked = resp.json()
    assert parked["status"] == "pending_approval"

    # approve -> executes for real
    approved = client.post(f"/v1/agent-runs/{parked['id']}/approve", headers=headers)
    assert approved.status_code == 200, approved.text
    result = approved.json()
    assert result["status"] == "succeeded"
    assert result["output"]["count"] >= 1
    assert all(s["provenance"].startswith("synthetic:") for s in result["output"]["samples"])

    # citation agent works synchronously
    resp = client.post("/v1/agents/citation/invoke", headers=headers, json={
        "params": {"text": "See doi:10.1234/example.5678 and arXiv:2106.09685 for details."},
    })
    citations = resp.json()["output"]["citations"]
    assert any(c["type"] == "doi" for c in citations)
    assert any(c["type"] == "arxiv" for c in citations)

    # security agent flags PII
    resp = client.post("/v1/agents/security/invoke", headers=headers, json={
        "params": {"text": "Email me at leak@example.com about the SSN 123-45-6789."},
    })
    output = resp.json()["output"]
    assert output["violations"]
    assert "leak@example.com" not in output["redacted_text"]


def test_auth_and_tenancy(client, auth):
    # unauthenticated requests rejected
    assert client.get("/v1/projects").status_code == 401
    # a second org cannot see the first org's projects
    other = client.post("/v1/auth/register", json={
        "org_name": "Rival Org", "email": "rival@test.dev", "password": "password123",
    }).json()
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}
    mine = client.get("/v1/projects", headers=auth["headers"]).json()["items"]
    theirs = client.get("/v1/projects", headers=other_headers).json()["items"]
    assert mine and not theirs
    # api keys work
    key = client.post("/v1/api-keys", headers=auth["headers"], json={"name": "ci"}).json()
    resp = client.get("/v1/projects", headers={"X-API-Key": key["key"]})
    assert resp.status_code == 200
    # admin surfaces
    metrics = client.get("/v1/admin/metrics", headers=auth["headers"]).json()
    assert metrics["resources"]["projects"] >= 1
    audit = client.get("/v1/admin/audit-logs", headers=auth["headers"]).json()["items"]
    assert any(a["action"] == "dataset.version.created" for a in audit)
    usage = client.get("/v1/admin/usage", headers=auth["headers"]).json()
    assert usage["agent_runs"] > 0
