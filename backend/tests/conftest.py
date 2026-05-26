"""Pytest configuration and shared fixtures.

Adds the backend root to sys.path so tests can `import main`, `from db import store`,
etc., regardless of the directory pytest is invoked from.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """A TestClient bound to the real FastAPI app."""
    from main import app
    return TestClient(app)
