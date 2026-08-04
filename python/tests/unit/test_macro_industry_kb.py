"""Tests for KB integration in macro_industry agent.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from valor.agents.macro_industry import _build_kb_section, _extract_citations


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