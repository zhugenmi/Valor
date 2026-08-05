"""Tests for KB API routes, corrections API, and SSE citations.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
import io
import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from valor.server.main import app
from valor.server.routes.stream import _extract_citations


@pytest.fixture
def upload_client(client, tmp_path, monkeypatch):
    """Client with KB files dir redirected to tmp_path."""
    from valor.knowledge_base import routes as kb_routes
    monkeypatch.setattr(kb_routes, "_get_files_dir", lambda: tmp_path)
    return client


@pytest.fixture
def corrections_client(tmp_path, monkeypatch):
    from valor.knowledge_base import routes as kb_routes
    monkeypatch.setattr(kb_routes, "_get_files_dir", lambda: tmp_path)
    from valor.server import db as dbmod
    monkeypatch.setattr(dbmod, "DB_PATH", tmp_path / "test.db")
    dbmod.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    dbmod.init_db()
    return TestClient(app)


# ---------------------------------------------------------------------------
# KB health + document CRUD routes
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Corrections API
# ---------------------------------------------------------------------------

def test_get_corrections_doc_not_found(corrections_client):
    resp = corrections_client.get("/api/v1/kb/documents/nonexistent/corrections")
    body = resp.json()
    assert body["code"] != 0


def test_delete_correction_idempotent(corrections_client):
    resp = corrections_client.delete("/api/v1/kb/corrections/nonexistent")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0


def test_get_corrections_after_insert(corrections_client):
    from valor.knowledge_base.kb_store import insert_document, insert_correction
    from valor.knowledge_base.models import KBDoc

    doc = KBDoc(
        doc_id="d1", title="t", category="disclosure", sub_type="quarterly_report",
        mime_type="application/pdf", file_path="x", sha256="abc",
        publish_date="2024-10-28", effective_until="2026-04-28",
        ticker="600519", uploaded_at=datetime.now(UTC).replace(tzinfo=None).isoformat(),
        status="ready", meta_json=json.dumps({"report_period": "2024Q3"}),
    )
    insert_document(doc)
    insert_correction(
        ticker="600519", report_period="2024Q3", field_name="revenue",
        original_value="1100.0", corrected_value="1238.45", unit="亿元",
        source_doc_id="d1", source_page=3,
    )
    resp = corrections_client.get("/api/v1/kb/documents/d1/corrections")
    body = resp.json()
    assert body["code"] == 0
    items = body["data"]
    assert len(items) == 1
    assert items[0]["field_name"] == "revenue"
    assert items[0]["corrected_value"] == "1238.45"


def test_delete_correction_removes_it(corrections_client):
    from valor.knowledge_base.kb_store import (
        get_corrections,
        insert_correction,
        insert_document,
    )
    from valor.knowledge_base.models import KBDoc

    doc = KBDoc(
        doc_id="d2", title="t", category="disclosure", sub_type="quarterly_report",
        mime_type="application/pdf", file_path="x", sha256="def",
        publish_date="2024-10-28", effective_until="2026-04-28",
        ticker="600519", uploaded_at=datetime.now(UTC).replace(tzinfo=None).isoformat(),
        status="ready", meta_json=json.dumps({"report_period": "2024Q3"}),
    )
    insert_document(doc)
    cid = insert_correction(
        ticker="600519", report_period="2024Q3", field_name="eps",
        original_value=None, corrected_value="1.23", unit="元",
        source_doc_id="d2", source_page=5,
    )
    resp = corrections_client.delete(f"/api/v1/kb/corrections/{cid}")
    assert resp.status_code == 200
    assert get_corrections("600519", "2024Q3") == []


# ---------------------------------------------------------------------------
# SSE citations
# ---------------------------------------------------------------------------

def test_extract_citations_empty_when_missing():
    assert _extract_citations({}, "macro_industry") == []


def test_extract_citations_from_dicts():
    state = {"metadata": {"macro_industry_citations": [
        {"chunk_id": "c1", "doc_id": "d1", "doc_title": "t",
         "publish_date": "2024-01-01", "vintage": "current", "cited_text": "x"},
    ]}}
    out = _extract_citations(state, "macro_industry")
    assert len(out) == 1
    assert out[0]["chunk_id"] == "c1"


def test_extract_citations_from_pydantic_models():
    from valor.core.protocols import Citation
    c = Citation(chunk_id="c2", doc_id="d2", doc_title="t",
                 publish_date="2024-01-01", vintage="current", cited_text="y")
    state = {"metadata": {"fundamentals_citations": [c]}}
    out = _extract_citations(state, "fundamentals")
    assert len(out) == 1
    assert out[0]["chunk_id"] == "c2"
    assert isinstance(out[0], dict)


def test_extract_citations_ignores_wrong_agent():
    state = {"metadata": {"macro_industry_citations": [{"chunk_id": "c1"}]}}
    assert _extract_citations(state, "fundamentals") == []