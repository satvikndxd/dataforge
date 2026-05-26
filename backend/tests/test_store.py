"""Tests for the in-memory job store."""
from db import store


def test_create_job_sets_defaults():
    job_id = store.create_job("solar energy", "json", 20, "text")
    job = store.get_job(job_id)
    assert job is not None
    assert job["topic"] == "solar energy"
    assert job["format"] == "json"
    assert job["num_sources"] == 20
    assert job["modality"] == "text"
    assert job["status"] == "pending"
    assert job["progress"] == 0


def test_create_job_defaults_modality_to_text():
    job_id = store.create_job("wind power", "csv", 15)
    assert store.get_job(job_id)["modality"] == "text"


def test_update_job_merges_fields():
    job_id = store.create_job("topic", "json", 10)
    store.update_job(job_id, status="done", progress=100, stage="Complete")
    job = store.get_job(job_id)
    assert job["status"] == "done"
    assert job["progress"] == 100
    assert job["stage"] == "Complete"
    assert job["topic"] == "topic"  # untouched fields remain


def test_get_missing_job_returns_none():
    assert store.get_job("not-a-real-id") is None


def test_update_missing_job_is_noop():
    # Should not raise even when the job does not exist.
    store.update_job("not-a-real-id", status="done")
    assert store.get_job("not-a-real-id") is None


def test_job_ids_are_unique():
    ids = {store.create_job("t", "json", 10) for _ in range(50)}
    assert len(ids) == 50
