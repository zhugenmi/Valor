"""Unit tests for market_data_agent industry/cluster wiring.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

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