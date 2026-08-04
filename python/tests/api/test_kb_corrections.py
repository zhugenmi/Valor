"""Tests for corrections API. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
import io
import json
from datetime import datetime

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


def test_get_corrections_doc_not_found(client):
    resp = client.get("/api/v1/kb/documents/nonexistent/corrections")
    body = resp.json()
    assert body["code"] != 0


def test_delete_correction_idempotent(client):
    resp = client.delete("/api/v1/kb/corrections/nonexistent")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0


def test_get_corrections_after_insert(client):
    from valor.knowledge_base.kb_store import insert_document, insert_correction
    from valor.knowledge_base.models import KBDoc

    doc = KBDoc(
        doc_id="d1", title="t", category="disclosure", sub_type="quarterly_report",
        mime_type="application/pdf", file_path="x", sha256="abc",
        publish_date="2024-10-28", effective_until="2026-04-28",
        ticker="600519", uploaded_at=datetime.utcnow().isoformat(),
        status="ready", meta_json=json.dumps({"report_period": "2024Q3"}),
    )
    insert_document(doc)
    insert_correction(
        ticker="600519", report_period="2024Q3", field_name="revenue",
        original_value="1100.0", corrected_value="1238.45", unit="亿元",
        source_doc_id="d1", source_page=3,
    )
    resp = client.get("/api/v1/kb/documents/d1/corrections")
    body = resp.json()
    assert body["code"] == 0
    items = body["data"]
    assert len(items) == 1
    assert items[0]["field_name"] == "revenue"
    assert items[0]["corrected_value"] == "1238.45"


def test_delete_correction_removes_it(client):
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
        ticker="600519", uploaded_at=datetime.utcnow().isoformat(),
        status="ready", meta_json=json.dumps({"report_period": "2024Q3"}),
    )
    insert_document(doc)
    cid = insert_correction(
        ticker="600519", report_period="2024Q3", field_name="eps",
        original_value=None, corrected_value="1.23", unit="元",
        source_doc_id="d2", source_page=5,
    )
    resp = client.delete(f"/api/v1/kb/corrections/{cid}")
    assert resp.status_code == 200
    assert get_corrections("600519", "2024Q3") == []
