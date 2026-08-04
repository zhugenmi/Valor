"""Tests for Signal.citations. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from valor.core.protocols import Citation, Signal


def test_signal_citations_default_empty():
    s = Signal(agent="test", signal="bullish", confidence=0.8, reasoning="x")
    assert s.citations == []


def test_signal_with_citations():
    c = Citation(chunk_id="c1", doc_id="d1", doc_title="研报",
                 publish_date="2024-10-28", vintage="current", cited_text="原文片段")
    s = Signal(agent="test", signal="bullish", confidence=0.8, reasoning="x", citations=[c])
    assert len(s.citations) == 1
    assert s.citations[0].chunk_id == "c1"


def test_citation_serialization():
    c = Citation(chunk_id="c1", doc_id="d1", doc_title="t",
                 publish_date="2024-01-01", vintage="current", cited_text="x", page_no=3)
    d = c.model_dump()
    assert d["page_no"] == 3
    assert d["vintage"] == "current"
