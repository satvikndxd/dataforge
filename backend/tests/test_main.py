"""Tests for the FastAPI application root and cross-cutting config (CORS, OpenAPI)."""


def test_root_returns_operational_message(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json() == {"message": "DataForge Backend is operational"}


def test_openapi_schema_is_served(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    assert resp.json()["info"]["title"] == "DataForge API"


def test_cors_preflight_allows_configured_origin(client):
    """The default CORS config allows http://localhost:3000."""
    resp = client.options(
        "/api/research",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.status_code in (200, 204)
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
