"""Unit tests for cluster-aware get_financial_metrics.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

import pytest

from valor.tools import api


def test_financial_cluster_adds_bank_special(monkeypatch: pytest.MonkeyPatch) -> None:
    """financial 集群追加银行专项指标."""
    monkeypatch.setattr(api, "get_valuation_indicator",
                        lambda s: {"pe_ttm": 5, "pb": 0.8, "market_cap": 1e10, "price": 10})
    monkeypatch.setattr(api, "get_financial_indicators",
                        lambda **kw: __import__("pandas").DataFrame(
                            {"日期": ["2024-01-01"], "净资产收益率(%)": [12]}))
    monkeypatch.setattr(api, "get_financial_report",
                        lambda s, t, **kw: __import__("pandas").DataFrame())
    monkeypatch.setattr(api, "get_dividend_yield", lambda s, p: 0.03)
    monkeypatch.setattr(api, "get_market_snapshot", lambda **kw: {})
    monkeypatch.setattr(api, "get_cache_refresh_flag", lambda *a, **kw: False)
    monkeypatch.setattr(api, "get_bank_special_indicators",
                        lambda s: {"net_interest_margin": 0.016, "non_performing_loan_ratio": 0.012})
    metrics = api.get_financial_metrics("600036", cluster_hint="financial")
    assert metrics[0]["net_interest_margin"] == 0.016
    assert metrics[0]["non_performing_loan_ratio"] == 0.012


def test_cyclical_cluster_adds_pb_percentile(monkeypatch: pytest.MonkeyPatch) -> None:
    """cyclical_resource 集群追加 PB 分位数."""
    monkeypatch.setattr(api, "get_valuation_indicator",
                        lambda s: {"pe_ttm": 8, "pb": 1.2, "market_cap": 1e10, "price": 20})
    monkeypatch.setattr(api, "get_financial_indicators",
                        lambda **kw: __import__("pandas").DataFrame(
                            {"日期": ["2024-01-01"], "净资产收益率(%)": [10]}))
    monkeypatch.setattr(api, "get_financial_report",
                        lambda s, t, **kw: __import__("pandas").DataFrame())
    monkeypatch.setattr(api, "get_dividend_yield", lambda s, p: 0.05)
    monkeypatch.setattr(api, "get_market_snapshot", lambda **kw: {})
    monkeypatch.setattr(api, "get_cache_refresh_flag", lambda *a, **kw: False)
    monkeypatch.setattr(api, "get_history_pb",
                        lambda s, years=5: [("2024-01-01", 1.0), ("2024-02-01", 1.5), ("2024-03-01", 2.0)])
    monkeypatch.setattr(api, "_compute_pb_percentile", lambda series, cur: 0.2)
    metrics = api.get_financial_metrics("601088", cluster_hint="cyclical_resource")
    assert metrics[0]["pb_percentile_5y"] == 0.2


def test_no_cluster_hint_returns_base_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    """无 cluster_hint 不追加专属指标."""
    monkeypatch.setattr(api, "get_valuation_indicator",
                        lambda s: {"pe_ttm": 10, "pb": 1.5, "market_cap": 1e10, "price": 15})
    monkeypatch.setattr(api, "get_financial_indicators",
                        lambda **kw: __import__("pandas").DataFrame(
                            {"日期": ["2024-01-01"], "净资产收益率(%)": [15]}))
    monkeypatch.setattr(api, "get_financial_report",
                        lambda s, t, **kw: __import__("pandas").DataFrame())
    monkeypatch.setattr(api, "get_dividend_yield", lambda s, p: 0.02)
    monkeypatch.setattr(api, "get_market_snapshot", lambda **kw: {})
    monkeypatch.setattr(api, "get_cache_refresh_flag", lambda *a, **kw: False)
    metrics = api.get_financial_metrics("600519")
    assert "net_interest_margin" not in metrics[0]
    assert "pb_percentile_5y" not in metrics[0]