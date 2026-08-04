"""Tests for fundamentals correction section. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from valor.agents._kb_helpers import build_correction_section


def test_correction_section_empty_when_no_corrections(monkeypatch):
    monkeypatch.setattr("valor.knowledge_base.corrector.get_corrections", lambda t, p: [])
    out = build_correction_section("600519", "2024Q3", {"chunks": []})
    assert out == ""


def test_correction_section_with_correction(monkeypatch):
    from valor.knowledge_base.models import CorrectionItem
    fake = CorrectionItem(
        correction_id="x", ticker="600519", report_period="2024Q3",
        field_name="revenue", original_value="1100.0", corrected_value="1238.45",
        unit="亿元", source_doc_id="d1", source_page=3,
        corrected_at="2026-08-03T00:00:00", reason="disclosure_authoritative",
    )
    monkeypatch.setattr("valor.knowledge_base.corrector.get_corrections", lambda t, p: [fake])
    kb_ctx = {"chunks": [{"doc_id": "d1"}]}
    out = build_correction_section("600519", "2024Q3", kb_ctx)
    assert "## 数据修正提示" in out
    assert "revenue" in out
    assert "1238.45" in out
    assert "[C1]" in out


def test_correction_section_empty_when_no_ticker():
    out = build_correction_section("", "2024Q3", {"chunks": []})
    assert out == ""


def test_correction_section_empty_when_no_period():
    out = build_correction_section("600519", "", {"chunks": []})
    assert out == ""


def test_correction_section_handles_missing_original(monkeypatch):
    from valor.knowledge_base.models import CorrectionItem
    fake = CorrectionItem(
        correction_id="y", ticker="600519", report_period="2024Q3",
        field_name="eps", original_value=None, corrected_value="1.23",
        unit="元", source_doc_id="d2", source_page=5,
        corrected_at="2026-08-03T00:00:00", reason="disclosure_authoritative",
    )
    monkeypatch.setattr("valor.knowledge_base.corrector.get_corrections", lambda t, p: [fake])
    out = build_correction_section("600519", "2024Q3", {"chunks": []})
    assert "eps" in out
    assert "1.23" in out
