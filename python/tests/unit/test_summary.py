"""Tests for valor.tools.summary builders.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from valor.tools.summary import (
    build_financial_summary,
    build_prices_summary,
    _monthly_resample,
)


# ---------------------------------------------------------------------------
# build_prices_summary
# ---------------------------------------------------------------------------


def _make_prices_df(n_days: int = 10) -> pd.DataFrame:
    """Build a synthetic daily K-line DataFrame for testing."""
    dates = pd.date_range("2026-01-01", periods=n_days, freq="D")
    return pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "open": [10.0 + i * 0.1 for i in range(n_days)],
        "high": [10.5 + i * 0.1 for i in range(n_days)],
        "low": [9.8 + i * 0.1 for i in range(n_days)],
        "close": [10.2 + i * 0.1 for i in range(n_days)],
        "volume": [10000 + i * 100 for i in range(n_days)],
    })


def test_prices_summary_empty_df():
    summary = build_prices_summary(pd.DataFrame(), "2026-01-01", "2026-12-31")
    assert summary["recent_5d"] == []
    assert summary["monthly_agg"] == []
    assert summary["statistics"]["highest"]["value"] == 0.0
    assert summary["statistics"]["avg_close"] == 0.0
    assert summary["time_range"]["trading_days"] == 0
    assert summary["time_range"]["start"] == "2026-01-01"
    assert summary["time_range"]["end"] == "2026-12-31"


def test_prices_summary_none_df():
    summary = build_prices_summary(None, "2026-01-01", "2026-12-31")
    assert summary["recent_5d"] == []
    assert summary["time_range"]["trading_days"] == 0


def test_prices_summary_recent_5d():
    df = _make_prices_df(10)
    summary = build_prices_summary(df, "2026-01-01", "2026-01-10")
    assert len(summary["recent_5d"]) == 5
    # Last 5 days: indices 5-9, close = 10.7, 10.8, 10.9, 11.0, 11.1
    assert summary["recent_5d"][0]["close"] == pytest.approx(10.7)
    assert summary["recent_5d"][-1]["close"] == pytest.approx(11.1)
    # Each record has the expected fields
    rec = summary["recent_5d"][0]
    assert "date" in rec
    assert "open" in rec
    assert "high" in rec
    assert "low" in rec
    assert "close" in rec
    assert "volume" in rec


def test_prices_summary_statistics_highest_lowest_with_date():
    df = _make_prices_df(10)
    summary = build_prices_summary(df, "2026-01-01", "2026-01-10")
    high = summary["statistics"]["highest"]
    low = summary["statistics"]["lowest"]
    # Highest high is on the last day (10.5 + 9*0.1 = 11.4)
    assert high["value"] == pytest.approx(11.4)
    assert high["date"] == "2026-01-10"
    # Lowest low is on the first day (9.8)
    assert low["value"] == pytest.approx(9.8)
    assert low["date"] == "2026-01-01"


def test_prices_summary_statistics_avg_close():
    df = _make_prices_df(10)
    summary = build_prices_summary(df, "2026-01-01", "2026-01-10")
    avg = summary["statistics"]["avg_close"]
    expected = sum(10.2 + i * 0.1 for i in range(10)) / 10
    assert avg == pytest.approx(expected)


def test_prices_summary_statistics_ytd_change():
    df = _make_prices_df(10)
    summary = build_prices_summary(df, "2026-01-01", "2026-01-10")
    ytd = summary["statistics"]["ytd_change"]
    # close[0] = 10.2, close[-1] = 11.1
    expected = 11.1 / 10.2 - 1
    assert ytd == pytest.approx(expected, rel=1e-3)


def test_prices_summary_statistics_annualized_volatility():
    df = _make_prices_df(10)
    summary = build_prices_summary(df, "2026-01-01", "2026-01-10")
    vol = summary["statistics"]["annualized_volatility"]
    assert vol >= 0.0  # volatility is non-negative
    assert not math.isnan(vol)


def test_prices_summary_time_range():
    df = _make_prices_df(10)
    summary = build_prices_summary(df, "2026-01-01", "2026-01-10")
    assert summary["time_range"]["start"] == "2026-01-01"
    assert summary["time_range"]["end"] == "2026-01-10"
    assert summary["time_range"]["trading_days"] == 10


def test_prices_summary_monthly_agg_last_12():
    # 60 days starting 2025-06-01 - should span 3 months (Jun/Jul/Aug)
    df = _make_prices_df(60)
    df["date"] = pd.date_range("2025-06-01", periods=60, freq="D").strftime("%Y-%m-%d")
    summary = build_prices_summary(df, "2025-06-01", "2025-07-30")
    monthly = summary["monthly_agg"]
    assert len(monthly) >= 1
    assert len(monthly) <= 12
    # Each monthly record should have OHLCV
    rec = monthly[0]
    assert "date" in rec
    assert "open" in rec
    assert "high" in rec
    assert "low" in rec
    assert "close" in rec
    assert "volume" in rec


def test_prices_summary_handles_nan_values():
    """NaN in close/high/low should not break summary computation."""
    df = _make_prices_df(10)
    df.loc[5, "close"] = float("nan")
    df.loc[5, "high"] = float("nan")
    summary = build_prices_summary(df, "2026-01-01", "2026-01-10")
    # Should not crash, avg_close computed from non-NaN closes
    assert summary["statistics"]["avg_close"] > 0.0


# ---------------------------------------------------------------------------
# build_financial_summary
# ---------------------------------------------------------------------------


def test_financial_summary_empty_input():
    assert build_financial_summary([], []) == {}
    assert build_financial_summary(None, None) == {}


def test_financial_summary_extracts_metrics_fields():
    metrics = [{
        "return_on_equity": 0.18,
        "net_margin": 0.22,
        "operating_margin": 0.15,
        "revenue_growth": 0.12,
        "earnings_growth": 0.10,
        "book_value_growth": 0.08,
        "current_ratio": 2.0,
        "debt_to_equity": 0.4,
        "free_cash_flow_per_share": 4.5,
        "earnings_per_share": 5.0,
        "pe_ratio": 22.5,
        "price_to_book": 3.0,
        "price_to_sales": 4.0,
        "dividend_yield": 0.0693,
        "book_value_per_share": 32.98,
        "payout_ratio": 1.386,
    }]
    line_items = [{
        "revenue": 1_000_000_000,
        "net_income": 220_000_000,
        "free_cash_flow": 180_000_000,
        "depreciation_and_amortization": 50_000_000,
        "capital_expenditure": 80_000_000,
    }]
    summary = build_financial_summary(metrics, line_items)

    assert summary["return_on_equity"] == pytest.approx(0.18)
    assert summary["net_margin"] == pytest.approx(0.22)
    assert summary["pe_ratio"] == pytest.approx(22.5)
    assert summary["price_to_book"] == pytest.approx(3.0)
    assert summary["revenue"] == pytest.approx(1_000_000_000)
    assert summary["net_income"] == pytest.approx(220_000_000)
    assert summary["free_cash_flow"] == pytest.approx(180_000_000)
    assert summary["dividend_yield"] == pytest.approx(0.0693)
    assert summary["book_value_per_share"] == pytest.approx(32.98)
    assert summary["payout_ratio"] == pytest.approx(1.386)


def test_financial_summary_handles_missing_fields():
    """Missing fields should be silently skipped, not raise."""
    metrics = [{"return_on_equity": 0.15}]  # only one field
    summary = build_financial_summary(metrics, [])
    assert "return_on_equity" in summary
    assert "pe_ratio" not in summary
    assert "revenue" not in summary
    assert "dividend_yield" not in summary
    assert "book_value_per_share" not in summary
    assert "payout_ratio" not in summary


def test_financial_summary_handles_none_values():
    """None values in metrics should be coerced to 0.0."""
    metrics = [{"return_on_equity": None, "pe_ratio": 20.0}]
    summary = build_financial_summary(metrics, [])
    assert summary["return_on_equity"] == 0.0
    assert summary["pe_ratio"] == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# _monthly_resample
# ---------------------------------------------------------------------------


def test_monthly_resample_empty_df():
    assert _monthly_resample(pd.DataFrame()) == []


def test_monthly_resample_missing_columns():
    df = pd.DataFrame({"date": ["2026-01-01"], "close": [10.0]})
    assert _monthly_resample(df) == []


def test_monthly_resample_aggregates_correctly():
    """Two days in January should aggregate to one monthly candle."""
    df = pd.DataFrame({
        "date": ["2026-01-10", "2026-01-20"],
        "open": [10.0, 11.0],
        "high": [10.5, 11.5],
        "low": [9.5, 10.5],
        "close": [10.2, 11.2],
        "volume": [1000, 2000],
    })
    monthly = _monthly_resample(df)
    assert len(monthly) == 1
    m = monthly[0]
    assert m["date"] == "2026-01-01"
    assert m["open"] == pytest.approx(10.0)  # first
    assert m["high"] == pytest.approx(11.5)  # max
    assert m["low"] == pytest.approx(9.5)  # min
    assert m["close"] == pytest.approx(11.2)  # last
    assert m["volume"] == pytest.approx(3000)  # sum
