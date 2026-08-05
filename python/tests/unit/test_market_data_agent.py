"""Unit tests for market_data_agent industry/cluster wiring.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from valor.agents import market_data as md_module
from valor.agents.market_data import market_data_agent


def _make_state(ticker="600036"):
    return {
        "messages": [],
        "data": {
            "ticker": ticker,
            "start_date": None,
            "end_date": None,
        },
        "metadata": {"show_reasoning": False},
    }


def test_market_data_writes_industry_and_cluster(monkeypatch: pytest.MonkeyPatch) -> None:
    """market_data_agent 获取行业+集群写入 state."""
    monkeypatch.setattr(md_module, "get_price_history", lambda *a, **kw: pd.DataFrame())
    monkeypatch.setattr(md_module, "get_market_snapshot", lambda *a, **kw: {})
    monkeypatch.setattr(md_module, "get_financial_metrics", lambda *a, **kw: [{"return_on_equity": 0.1}])
    monkeypatch.setattr(md_module, "get_financial_statements", lambda *a, **kw: [{}, {}])
    monkeypatch.setattr(md_module, "get_market_data", lambda *a, **kw: {"market_cap": 1e10})
    monkeypatch.setattr(md_module, "resolve_stock", lambda s: ("银行", "financial"))
    monkeypatch.setattr(md_module, "build_prices_summary", lambda *a, **kw: {})
    monkeypatch.setattr(md_module, "build_financial_summary", lambda *a, **kw: {})
    monkeypatch.setattr(md_module, "get_latest_trading_day", lambda d: d)

    result = market_data_agent(_make_state("600036"))
    assert result["data"]["industry"] == "银行"
    assert result["data"]["cluster"] == "financial"


def test_market_data_defaults_to_conglomerate_on_missing_industry(monkeypatch: pytest.MonkeyPatch) -> None:
    """行业获取失败时 fallback 到 conglomerate."""
    monkeypatch.setattr(md_module, "get_price_history", lambda *a, **kw: pd.DataFrame())
    monkeypatch.setattr(md_module, "get_market_snapshot", lambda *a, **kw: {})
    monkeypatch.setattr(md_module, "get_financial_metrics", lambda *a, **kw: [{}])
    monkeypatch.setattr(md_module, "get_financial_statements", lambda *a, **kw: [{}, {}])
    monkeypatch.setattr(md_module, "get_market_data", lambda *a, **kw: {"market_cap": 0})
    monkeypatch.setattr(md_module, "resolve_stock", lambda s: (None, "conglomerate"))
    monkeypatch.setattr(md_module, "build_prices_summary", lambda *a, **kw: {})
    monkeypatch.setattr(md_module, "build_financial_summary", lambda *a, **kw: {})
    monkeypatch.setattr(md_module, "get_latest_trading_day", lambda d: d)

    result = market_data_agent(_make_state("999999"))
    assert result["data"]["industry"] is None
    assert result["data"]["cluster"] == "conglomerate"


def test_market_data_passes_cluster_hint_to_financial_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    """market_data_agent 将 cluster_hint 传递给 get_financial_metrics."""
    monkeypatch.setattr(md_module, "get_price_history", lambda *a, **kw: pd.DataFrame())
    monkeypatch.setattr(md_module, "get_market_snapshot", lambda *a, **kw: {})
    monkeypatch.setattr(md_module, "get_financial_statements", lambda *a, **kw: [{}, {}])
    monkeypatch.setattr(md_module, "get_market_data", lambda *a, **kw: {"market_cap": 1e10})
    monkeypatch.setattr(md_module, "resolve_stock", lambda s: ("电子", "tmt"))
    monkeypatch.setattr(md_module, "build_prices_summary", lambda *a, **kw: {})
    monkeypatch.setattr(md_module, "build_financial_summary", lambda *a, **kw: {})
    monkeypatch.setattr(md_module, "get_latest_trading_day", lambda d: d)

    received_cluster_hint = []

    def capture_financial_metrics(*a, **kw):
        received_cluster_hint.append(kw.get("cluster_hint"))
        return [{"return_on_equity": 0.1}]

    monkeypatch.setattr(md_module, "get_financial_metrics", capture_financial_metrics)

    market_data_agent(_make_state("002475"))
    assert len(received_cluster_hint) == 1
    assert received_cluster_hint[0] == "tmt"


def _latest_day_build_state(end_date=None):
    return {
        "messages": [],
        "data": {
            "ticker": "600519",
            "start_date": None,
            "end_date": end_date,
        },
        "metadata": {"show_reasoning": False},
    }


def test_default_end_date_uses_latest_trading_day():
    """If data.end_date is None, agent should resolve to get_latest_trading_day(),
    not just yesterday. On 2026-07-20 (Mon) -> 2026-07-17 (Fri)."""
    with (
        patch("valor.agents.market_data.get_price_history", return_value=None),
        patch("valor.agents.market_data.get_market_data", return_value={"market_cap": 0}),
        patch("valor.agents.market_data.get_financial_metrics", return_value=[]),
        patch("valor.agents.market_data.get_financial_statements", return_value=[]),
        patch("valor.agents.market_data.get_market_snapshot", return_value=None),
        patch(
            "valor.agents.market_data.get_latest_trading_day",
            return_value=date(2026, 7, 17),
        ),
        patch("valor.agents.market_data.datetime") as mock_dt,
    ):
        from datetime import datetime as real_dt

        mock_dt.now.return_value = real_dt(2026, 7, 20, 10, 0, 0)
        mock_dt.side_effect = real_dt
        mock_dt.strptime = real_dt.strptime

        result = market_data_agent(_latest_day_build_state(end_date=None))

    # Before fix: end_date = yesterday = "2026-07-19" (Sunday) -> FAIL
    # After fix: end_date = latest trading day = "2026-07-17" (Friday) -> PASS
    assert result["data"]["end_date"] == "2026-07-17"


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