"""Tests for KB API routes. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
import io

import pytest
from fastapi.testclient import TestClient

from valor.server.main import app


@pytest.fixture
def upload_client(client, tmp_path, monkeypatch):
    """Client with KB files dir redirected to tmp_path."""
    from valor.knowledge_base import routes as kb_routes
    monkeypatch.setattr(kb_routes, "_get_files_dir", lambda: tmp_path)
    return client


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
    from valor.server.db import KB_AVAILABLE
    if KB_AVAILABLE:
        pytest.skip("sqlite-vec available, skip 503 test")
    # KB_AVAILABLE is False -> endpoint should return 503
    client = TestClient(app)
    resp = client.get("/api/v1/kb/health")
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Task 2.9: document CRUD tests
# ---------------------------------------------------------------------------


def test_upload_text_document(upload_client, tmp_path):
    content = "# 测试标题\n第一段内容。\n第二段内容。"
    resp = upload_client.post(
        "/api/v1/kb/documents",
        data={"title": "测试文档", "category": "research", "sub_type": "公司研究",
              "publish_date": "2024-10-28"},
        files={"file": ("test.md", io.BytesIO(content.encode("utf-8")), "text/markdown")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["doc_id"]
    assert body["data"]["status"] in ("indexing", "ready")


def test_upload_duplicate_sha256_rejected(upload_client):
    content = "重复内容"
    resp1 = upload_client.post(
        "/api/v1/kb/documents",
        data={"title": "t1", "category": "research", "sub_type": "公司研究"},
        files={"file": ("a.txt", io.BytesIO(content.encode("utf-8")), "text/plain")},
    )
    assert resp1.json()["code"] == 0
    resp2 = upload_client.post(
        "/api/v1/kb/documents",
        data={"title": "t2", "category": "research", "sub_type": "公司研究"},
        files={"file": ("b.txt", io.BytesIO(content.encode("utf-8")), "text/plain")},
    )
    assert resp2.json()["code"] != 0
    assert "exists" in resp2.json()["msg"].lower() or "duplicate" in resp2.json()["msg"].lower()


def test_list_documents(upload_client):
    for i in range(3):
        upload_client.post(
            "/api/v1/kb/documents",
            data={"title": f"t{i}", "category": "research", "sub_type": "公司研究"},
            files={"file": (f"a{i}.txt", io.BytesIO(f"内容{i}".encode("utf-8")), "text/plain")},
        )
    resp = upload_client.get("/api/v1/kb/documents?limit=10")
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["total"] >= 3


def test_get_document_detail(upload_client):
    upload = upload_client.post(
        "/api/v1/kb/documents",
        data={"title": "详情测试", "category": "research", "sub_type": "公司研究"},
        files={"file": ("a.txt", io.BytesIO(b"content"), "text/plain")},
    )
    doc_id = upload.json()["data"]["doc_id"]
    resp = upload_client.get(f"/api/v1/kb/documents/{doc_id}")
    assert resp.status_code == 200
    assert resp.json()["data"]["doc_id"] == doc_id


def test_delete_document(upload_client):
    upload = upload_client.post(
        "/api/v1/kb/documents",
        data={"title": "删除测试", "category": "research", "sub_type": "公司研究"},
        files={"file": ("a.txt", io.BytesIO(b"delete me"), "text/plain")},
    )
    doc_id = upload.json()["data"]["doc_id"]
    resp = upload_client.delete(f"/api/v1/kb/documents/{doc_id}")
    assert resp.status_code == 200
    # Verify gone
    get_resp = upload_client.get(f"/api/v1/kb/documents/{doc_id}")
    assert get_resp.json()["code"] != 0


def test_get_categories(upload_client):
    resp = upload_client.get("/api/v1/kb/categories")
    body = resp.json()
    assert body["code"] == 0
    assert len(body["data"]["categories"]) == 4


def test_get_chunks(upload_client):
    upload = upload_client.post(
        "/api/v1/kb/documents",
        data={"title": "chunks", "category": "research", "sub_type": "公司研究"},
        files={"file": ("a.txt", io.BytesIO("第一段。第二段。".encode("utf-8")), "text/plain")},
    )
    doc_id = upload.json()["data"]["doc_id"]
    # Wait for indexing (synchronous in test)
    resp = upload_client.get(f"/api/v1/kb/documents/{doc_id}/chunks")
    assert resp.status_code == 200