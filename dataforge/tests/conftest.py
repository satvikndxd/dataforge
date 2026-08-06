"""Test fixtures: isolated SQLite DB + storage per session, app client."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_tmp = tempfile.mkdtemp(prefix="dataforge-test-")
os.environ["DATAFORGE_DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["DATAFORGE_STORAGE_ROOT"] = f"{_tmp}/storage"
os.environ["DATAFORGE_SECRET_KEY"] = "test-secret"
os.environ["DATAFORGE_RESPECT_ROBOTS_TXT"] = "false"
os.environ.pop("ANTHROPIC_API_KEY", None)


@pytest.fixture(scope="session")
def app():
    from backend.core.config import reset_settings_cache

    reset_settings_cache()
    from backend.db.base import init_db

    init_db()
    from apps.api.main import app as fastapi_app

    return fastapi_app


@pytest.fixture(scope="session")
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def auth(client):
    """Registered org + auth headers."""
    resp = client.post("/v1/auth/register", json={
        "org_name": "Test Org", "email": "owner@test.dev",
        "password": "s3cure-pass", "name": "Owner",
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()
    return {"headers": {"Authorization": f"Bearer {data['access_token']}"}, **data}
