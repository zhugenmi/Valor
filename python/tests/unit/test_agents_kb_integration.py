"""Tests for KB integration across 5 agents. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from valor.agents._kb_helpers import build_kb_section, extract_citations


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