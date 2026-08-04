"""Tests for KB API routes. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
import pytest
from fastapi.testclient import TestClient

from valor.server.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_kb_health_returns_200(client):
    from valor.server.db import KB_AVAILABLE
    if not KB_AVAILABLE:
        pytest.skip("sqlite-vec not available, skip 200 test")
    resp = client.get("/api/v1/kb/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert "sqlite_vec" in data
    assert "fts5" in data
    assert "embedder" in data
    assert "reranker" in data
    assert data["sqlite_vec"] in ["ok", "unavailable"]
    assert data["fts5"] == "ok"


def test_kb_health_when_vec_unavailable_returns_503(monkeypatch):
    """When sqlite-vec not loaded, /kb/health returns 503."""
    from valor.knowledge_base import routes as kb_routes
    from valor.server.db import KB_AVAILABLE
    if KB_AVAILABLE:
        pytest.skip("sqlite-vec available, skip 503 test")
    # KB_AVAILABLE is False -> endpoint should return 503
    from fastapi.testclient import TestClient
    from valor.server.main import app
    client = TestClient(app)
    resp = client.get("/api/v1/kb/health")
    assert resp.status_code == 503