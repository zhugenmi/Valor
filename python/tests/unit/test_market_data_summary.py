"""Tests for market_data_agent prices_summary/financial_summary output.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from valor.agents.market_data import market_data_agent


def _build_state(end_date="2026-07-17"):
    return {
        "messages": [],
        "data": {
            "ticker": "600519",
            "start_date": None,
            "end_date": end_date,
        },
        "metadata": {"show_reasoning": False},
    }


def _make_prices_df(n_days: int = 10) -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=n_days, freq="D").strftime("%Y-%m-%d"),
        "open": [10.0 + i * 0.1 for i in range(n_days)],
        "high": [10.5 + i * 0.1 for i in range(n_days)],
        "low": [9.8 + i * 0.1 for i in range(n_days)],
        "close": [10.2 + i * 0.1 for i in range(n_days)],
        "volume": [10000 + i * 100 for i in range(n_days)],
    })


def test_market_data_output_includes_prices_summary():
    """market_data_agent should write prices_summary to state.data."""
    prices_df = _make_prices_df(10)
    with (
        patch("valor.agents.market_data.get_price_history", return_value=prices_df),
        patch("valor.agents.market_data.get_market_data", return_value={"market_cap": 1_500_000_000}),
        patch("valor.agents.market_data.get_financial_metrics", return_value=[]),
        patch("valor.agents.market_data.get_financial_statements", return_value=[]),
        patch("valor.agents.market_data.get_market_snapshot", return_value=None),
    ):
        result = market_data_agent(_build_state())

    assert "prices_summary" in result["data"]
    summary = result["data"]["prices_summary"]
    assert "recent_5d" in summary
    assert "monthly_agg" in summary
    assert "statistics" in summary
    assert "time_range" in summary
    assert summary["time_range"]["trading_days"] == 10
    # prices (full K-line) should still be present for downstream agents
    assert "prices" in result["data"]
    assert len(result["data"]["prices"]) == 10


def test_market_data_output_includes_financial_summary():
    """market_data_agent should write financial_summary to state.data."""
    prices_df = _make_prices_df(10)
    metrics = [{
        "return_on_equity": 0.18,
        "net_margin": 0.22,
        "pe_ratio": 22.5,
        "price_to_book": 3.0,
        "dividend_yield": 0.0693,
        "book_value_per_share": 32.98,
        "payout_ratio": 1.386,
    }]
    line_items = [{
        "revenue": 1_000_000_000,
        "net_income": 220_000_000,
        "free_cash_flow": 180_000_000,
    }]
    with (
        patch("valor.agents.market_data.get_price_history", return_value=prices_df),
        patch("valor.agents.market_data.get_market_data", return_value={"market_cap": 1_500_000_000}),
        patch("valor.agents.market_data.get_financial_metrics", return_value=metrics),
        patch("valor.agents.market_data.get_financial_statements", return_value=line_items),
        patch("valor.agents.market_data.get_market_snapshot", return_value=None),
    ):
        result = market_data_agent(_build_state())

    assert "financial_summary" in result["data"]
    fs = result["data"]["financial_summary"]
    assert fs["return_on_equity"] == 0.18
    assert fs["pe_ratio"] == 22.5
    assert fs["revenue"] == 1_000_000_000
    assert fs["net_income"] == 220_000_000
    assert fs["dividend_yield"] == 0.0693
    assert fs["book_value_per_share"] == 32.98
    assert fs["payout_ratio"] == 1.386


def test_market_data_prices_summary_handles_empty_prices():
    """Empty prices DataFrame should yield empty summary, not raise."""
    with (
        patch("valor.agents.market_data.get_price_history", return_value=pd.DataFrame()),
        patch("valor.agents.market_data.get_market_data", return_value={"market_cap": 0}),
        patch("valor.agents.market_data.get_financial_metrics", return_value=[]),
        patch("valor.agents.market_data.get_financial_statements", return_value=[]),
        patch("valor.agents.market_data.get_market_snapshot", return_value=None),
    ):
        result = market_data_agent(_build_state())

    summary = result["data"]["prices_summary"]
    assert summary["recent_5d"] == []
    assert summary["monthly_agg"] == []
    assert summary["time_range"]["trading_days"] == 0


def test_market_data_financial_summary_empty_when_no_metrics():
    """No financial metrics should yield empty financial_summary dict."""
    prices_df = _make_prices_df(5)
    with (
        patch("valor.agents.market_data.get_price_history", return_value=prices_df),
        patch("valor.agents.market_data.get_market_data", return_value={"market_cap": 0}),
        patch("valor.agents.market_data.get_financial_metrics", return_value=[]),
        patch("valor.agents.market_data.get_financial_statements", return_value=[]),
        patch("valor.agents.market_data.get_market_snapshot", return_value=None),
    ):
        result = market_data_agent(_build_state())

    assert result["data"]["financial_summary"] == {}
