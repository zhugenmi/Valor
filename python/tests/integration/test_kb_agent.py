"""Integration: /api/v1/kb/search endpoint. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
import io

import pytest
from fastapi.testclient import TestClient

from valor.server.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    from valor.knowledge_base import routes as kb_routes
    monkeypatch.setattr(kb_routes, "_get_files_dir", lambda: tmp_path)
    from valor.server import db as dbmod
    monkeypatch.setattr(dbmod, "DB_PATH", tmp_path / "test.db")
    dbmod.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    dbmod.init_db()
    return TestClient(app)


def test_kb_search_endpoint(client):
    content = "贵州茅台 2024Q3 营收增长 15%"
    client.post(
        "/api/v1/kb/documents",
        data={"title": "茅台研报", "category": "research", "sub_type": "公司研究",
              "publish_date": "2024-10-28"},
        files={"file": ("test.md", io.BytesIO(content.encode("utf-8")), "text/markdown")},
    )
    resp = client.post("/api/v1/kb/search", json={"query": "茅台营收", "top_k": 3})
    body = resp.json()
    assert body["code"] == 0
    assert "chunks" in body["data"]


def test_kb_search_empty_query_rejected(client):
    resp = client.post("/api/v1/kb/search", json={"query": ""})
    assert resp.json()["code"] != 0
