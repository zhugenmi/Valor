"""Tests for verify_and_correct. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
import json
from datetime import datetime

import pytest

from valor.knowledge_base.corrector import (
    get_corrections,
    verify_and_correct_for_doc,
)
from valor.knowledge_base.kb_store import insert_document
from valor.knowledge_base.models import KBDoc
from valor.knowledge_base.parser import ParsedDocument, ParsedPage, ParsedTable
from valor.server.db import init_db


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    from valor.server import db as dbmod
    monkeypatch.setattr(dbmod, "DB_PATH", tmp_path / "test.db")
    dbmod.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    init_db()
    return dbmod


def test_verify_writes_correction_when_diff_exceeds_tolerance(fresh_db, monkeypatch):
    doc = KBDoc(
        doc_id="d1", title="茅台Q3", category="disclosure", sub_type="quarterly_report",
        mime_type="application/pdf", file_path="x", sha256="abc",
        publish_date="2024-10-28", effective_until="2026-04-28",
        ticker="600519", uploaded_at=datetime.utcnow().isoformat(),
        status="ready", meta_json=json.dumps({"report_period": "2024Q3", "enable_correction": True}),
    )
    insert_document(doc)
    parsed = ParsedDocument(
        file_path="x", mime_type="application/pdf",
        pages=[ParsedPage(page_no=1, text="主要会计数据")],
        full_text="主要会计数据",
        tables=[ParsedTable(page_no=1, rows=[
            ["项目", "本期金额"],
            ["营业收入", "1238.45"],
        ])],
    )

    async def mock_get_financial_indicators(self, ticker):
        return {"revenue": 1100.0}

    from valor.adapters.data import router as data_router_mod
    monkeypatch.setattr(
        data_router_mod.DataRouter, "get_financial_indicators",
        mock_get_financial_indicators,
    )

    count = verify_and_correct_for_doc("d1", parsed)
    assert count >= 1
    corrections = get_corrections("600519", "2024Q3")
    assert any(c.field_name == "revenue" for c in corrections)
    rev_corr = next(c for c in corrections if c.field_name == "revenue")
    assert rev_corr.original_value == "1100.0"
    assert rev_corr.corrected_value == "1238.45"


def test_verify_skips_when_within_tolerance(fresh_db, monkeypatch):
    doc = KBDoc(
        doc_id="d2", title="t", category="disclosure", sub_type="quarterly_report",
        mime_type="application/pdf", file_path="x", sha256="def",
        publish_date="2024-10-28", effective_until="2026-04-28",
        ticker="600519", uploaded_at=datetime.utcnow().isoformat(),
        status="ready", meta_json=json.dumps({"report_period": "2024Q3", "enable_correction": True}),
    )
    insert_document(doc)
    parsed = ParsedDocument(
        file_path="x", mime_type="application/pdf",
        pages=[], full_text="",
        tables=[ParsedTable(page_no=1, rows=[
            ["项目", "金额"], ["营业收入", "100.5"],
        ])],
    )

    async def mock_get(self, ticker):
        return {"revenue": 100.4}

    from valor.adapters.data import router as data_router_mod
    monkeypatch.setattr(data_router_mod.DataRouter, "get_financial_indicators", mock_get)
    count = verify_and_correct_for_doc("d2", parsed)
    assert count == 0


def test_verify_skips_non_disclosure(fresh_db, monkeypatch):
    doc = KBDoc(
        doc_id="d3", title="研报", category="research", sub_type="公司研究",
        mime_type="application/pdf", file_path="x", sha256="ghi",
        publish_date="2024-10-28", effective_until="2026-04-28",
        ticker="600519", uploaded_at=datetime.utcnow().isoformat(),
        status="ready", meta_json=json.dumps({"report_period": "2024Q3", "enable_correction": True}),
    )
    insert_document(doc)
    parsed = ParsedDocument(
        file_path="x", mime_type="application/pdf",
        pages=[], full_text="",
        tables=[ParsedTable(page_no=1, rows=[["项目", "金额"], ["营业收入", "100"]])],
    )
    count = verify_and_correct_for_doc("d3", parsed)
    assert count == 0
