"""Tests for KB integration across agents.

Covers the shared KB helpers (_kb_helpers), the fundamentals correction
section, the macro/industry agent wiring, and the kb_retrieval workflow node.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from valor.agents._kb_helpers import (
    build_correction_section,
    build_kb_section,
    extract_citations,
)
from valor.agents._kb_helpers import build_kb_section as _build_kb_section
from valor.agents._kb_helpers import extract_citations as _extract_citations
from valor.agents.workflow import _run_kb_retrieval


def test_build_kb_section_consistent_across_agents():
    """All agents use the same helper, so output format is identical."""
    kb_ctx = {
        "chunks": [
            {"chunk_id": "c1", "doc_id": "d1", "doc_title": "研报",
             "publish_date": "2024-10-28", "vintage": "current",
             "page_no": 1, "text": "内容"},
        ]
    }
    out = build_kb_section(kb_ctx)
    assert "[C1]" in out
    assert "研报" in out


def test_extract_citations_handles_empty():
    assert extract_citations("no refs", {"chunks": []}) == []
    assert extract_citations("[C1]", {"skipped": True}) == []


def test_build_kb_section_empty_when_skipped():
    """_build_kb_section returns empty string when kb_ctx has skipped=True."""
    kb_ctx = {"skipped": True, "reason": "low_relevance"}
    assert _build_kb_section(kb_ctx) == ""


def test_build_kb_section_empty_when_no_chunks():
    """_build_kb_section returns empty string when chunks is empty list."""
    kb_ctx = {"chunks": []}
    assert _build_kb_section(kb_ctx) == ""


def test_build_kb_section_with_chunks():
    """_build_kb_section formats chunks into a markdown section."""
    kb_ctx = {
        "chunks": [
            {
                "chunk_id": "c1",
                "doc_id": "d1",
                "doc_title": "2026年货币政策报告",
                "publish_date": "2026-06-15",
                "vintage": "current",
                "page_no": 3,
                "heading_path": "货币政策 / 利率",
                "text": "央行维持LPR不变，市场流动性充裕。",
                "score": 0.92,
            },
            {
                "chunk_id": "c2",
                "doc_id": "d2",
                "doc_title": "新能源行业白皮书",
                "publish_date": "2026-05-01",
                "vintage": "recent",
                "page_no": None,
                "heading_path": "行业展望",
                "text": "光伏装机量同比增长30%。",
                "score": 0.85,
            },
        ]
    }
    result = _build_kb_section(kb_ctx)
    assert "## 知识库参考" in result
    assert "[C1]" in result
    assert "2026年货币政策报告" in result
    assert "current" in result
    assert "[C2]" in result
    assert "新能源行业白皮书" in result
    assert "recent" in result
    assert "光伏装机量同比增长30%" in result


def test_extract_citations_maps_c1():
    """_extract_citations maps [C1] references to the correct chunk."""
    kb_ctx = {
        "chunks": [
            {
                "chunk_id": "c1",
                "doc_id": "d1",
                "doc_title": "宏观报告",
                "publish_date": "2026-07-01",
                "vintage": "current",
                "page_no": 5,
                "heading_path": "政策",
                "text": "降准释放流动性5000亿元。",
                "score": 0.95,
            },
        ]
    }
    text = "根据[C1]的分析，货币政策宽松。"
    citations = _extract_citations(text, kb_ctx)
    assert len(citations) == 1
    cit = citations[0]
    assert cit.chunk_id == "c1"
    assert cit.doc_id == "d1"
    assert cit.doc_title == "宏观报告"
    assert cit.publish_date == "2026-07-01"
    assert cit.vintage == "current"
    assert cit.page_no == 5
    assert cit.cited_text == "降准释放流动性5000亿元。"


def test_extract_citations_ignores_unknown_refs():
    """_extract_citations ignores [Cn] references that have no matching chunk."""
    kb_ctx = {
        "chunks": [
            {
                "chunk_id": "c1",
                "doc_id": "d1",
                "doc_title": "报告A",
                "publish_date": "2026-07-01",
                "vintage": "current",
                "page_no": 1,
                "heading_path": "概述",
                "text": "内容A",
                "score": 0.9,
            },
        ]
    }
    text = "[C1]是正确的，[C5]是臆造的。"
    citations = _extract_citations(text, kb_ctx)
    assert len(citations) == 1
    assert citations[0].chunk_id == "c1"


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


def test_kb_retrieval_disabled_returns_empty():
    state = {
        "messages": [],
        "data": {"ticker": "600519"},
        "metadata": {"kb_enabled": False},
    }
    result = _run_kb_retrieval(state)
    assert result["data"]["kb_context"] == {}


def test_kb_retrieval_disabled_by_default_flag():
    """When kb_enabled missing, default to True but no KB data -> skipped per agent."""
    state = {
        "messages": [],
        "data": {"ticker": "600519"},
        "metadata": {},
    }
    result = _run_kb_retrieval(state)
    # kb_context is a dict, may be empty if retriever returns nothing (no KB data in test DB)
    assert "kb_context" in result["data"]


def test_kb_retrieval_respects_custom_agent_list():
    state = {
        "messages": [],
        "data": {"ticker": "600519"},
        "metadata": {"kb_agents": ["technicals"]},
    }
    result = _run_kb_retrieval(state)
    assert "kb_context" in result["data"]
    # Only technicals should be in context
    assert set(result["data"]["kb_context"].keys()) <= {"technicals"}