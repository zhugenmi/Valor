"""Tests for kb_search tool. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from valor.tools.kb_search import search


def test_search_returns_list():
    results = search("nonexistent query xyz", top_k=3)
    assert isinstance(results, list)
    # Each item is dict if non-empty
    for r in results:
        assert isinstance(r, dict)
        assert "chunk_id" in r
        assert "text" in r
