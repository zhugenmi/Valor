"""Tests for stream.py _filter_state_delta helper.

Verifies that raw data fields (prices, financial_metrics,
financial_line_items, market_data) are stripped from SSE/DB payload
while analysis results, messages, and metadata are preserved.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from __future__ import annotations

from valor.server.routes.stream import _filter_state_delta


def test_filter_strips_prices_from_data():
    """data.prices should be removed (it's the largest raw payload)."""
    state_delta = {
        "messages": [],
        "data": {
            "ticker": "600519",
            "prices": [{"date": "2026-01-01", "close": 10.0}] * 365,
            "prices_summary": {"statistics": {"avg_close": 10.5}},
            "technical_analysis": {"signal": "bullish"},
        },
        "metadata": {"show_reasoning": False},
    }
    filtered = _filter_state_delta(state_delta)
    assert "prices" not in filtered["data"]
    assert filtered["data"]["ticker"] == "600519"
    assert filtered["data"]["prices_summary"]["statistics"]["avg_close"] == 10.5
    assert filtered["data"]["technical_analysis"]["signal"] == "bullish"


def test_filter_strips_all_raw_data_fields():
    """All 4 raw data fields should be stripped."""
    state_delta = {
        "data": {
            "prices": [{"close": 10.0}],
            "financial_metrics": [{"roe": 0.15}],
            "financial_line_items": [{"net_income": 1e8}],
            "market_data": {"market_cap": 1e10, "volume": 1e6},
            "financial_summary": {"roe": 0.15},
        },
    }
    filtered = _filter_state_delta(state_delta)
    data = filtered["data"]
    assert "prices" not in data
    assert "financial_metrics" not in data
    assert "financial_line_items" not in data
    assert "market_data" not in data
    # financial_summary is NOT in exclude list, should be preserved
    assert "financial_summary" in data


def test_filter_preserves_market_cap():
    """market_cap is a single float used by frontend, should be preserved."""
    state_delta = {
        "data": {
            "market_cap": 1_500_000_000.0,
            "ticker": "600519",
        },
    }
    filtered = _filter_state_delta(state_delta)
    assert filtered["data"]["market_cap"] == 1_500_000_000.0


def test_filter_preserves_messages_and_metadata():
    """messages and metadata should pass through unchanged."""
    msgs = [{"name": "technical_analyst_agent", "content": "{}"}]
    meta = {"show_reasoning": True, "model": "openai"}
    state_delta = {
        "messages": msgs,
        "data": {"technical_analysis": {"signal": "bullish"}},
        "metadata": meta,
    }
    filtered = _filter_state_delta(state_delta)
    assert filtered["messages"] == msgs
    assert filtered["metadata"] == meta


def test_filter_preserves_unknown_data_fields():
    """Future non-raw data fields should pass through (exclude blacklist)."""
    state_delta = {
        "data": {
            "new_analysis_field": {"signal": "neutral"},
            "another_field": 42,
        },
    }
    filtered = _filter_state_delta(state_delta)
    assert filtered["data"]["new_analysis_field"]["signal"] == "neutral"
    assert filtered["data"]["another_field"] == 42


def test_filter_handles_non_dict_input():
    """Non-dict input should be returned as-is (defensive)."""
    assert _filter_state_delta(None) is None
    assert _filter_state_delta([]) == []
    assert _filter_state_delta("string") == "string"


def test_filter_handles_missing_data_key():
    """State_delta without 'data' key should pass through unchanged."""
    state_delta = {"messages": [], "metadata": {}}
    filtered = _filter_state_delta(state_delta)
    assert filtered == state_delta


def test_filter_preserves_analysis_result_fields():
    """All agent analysis result fields should be preserved."""
    state_delta = {
        "data": {
            "technical_analysis": {"signal": "bullish", "evidence": {"adx": 28.5}},
            "fundamental_analysis": {"signal": "neutral", "evidence": {"roe": 0.18}},
            "valuation_analysis": {"signal": "bearish", "evidence": {"dcf_gap": -0.25}},
            "risk_analysis": {"signal": "hold", "evidence": {"volatility": 0.32}},
            "debate_analysis": {"signal": "neutral"},
            "capital_sentiment_analysis": {"signal": "bullish", "evidence": []},
            "macro_industry_analysis": {"signal": "neutral", "evidence": []},
        },
    }
    filtered = _filter_state_delta(state_delta)
    data = filtered["data"]
    for key in ("technical_analysis", "fundamental_analysis",
                "valuation_analysis", "risk_analysis", "debate_analysis",
                "capital_sentiment_analysis", "macro_industry_analysis"):
        assert key in data, f"{key} should be preserved"
    # evidence fields should survive
    assert data["technical_analysis"]["evidence"]["adx"] == 28.5
    assert data["fundamental_analysis"]["evidence"]["roe"] == 0.18
