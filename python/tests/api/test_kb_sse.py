"""Tests for SSE citations. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from valor.server.routes.stream import _extract_citations


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
