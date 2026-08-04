"""Tests for kb_retrieval node. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from valor.agents.workflow import _run_kb_retrieval


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
