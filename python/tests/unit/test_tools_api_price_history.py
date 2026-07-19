"""Tests for get_price_history widen-range behavior.

Bug A regression: when the initial fetch returns fewer than 120 rows,
get_price_history widens the range to 730 days to feed technical indicators
(momentum_6m, hurst, volatility_regime, etc.) enough history. Before the
fix, the widened df was returned directly to callers, causing downstream
consumers (frontend analysisExtractor) to compute max/min/avg/count over
2 years of data while displaying only the user-requested 1-month range.

The fix masks the widened df back to the original [start, end] window
before returning, so technical indicators still see the wider history
but callers only get the rows they asked for.
"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from valor.tools import api as api_module


def _make_kline_df(symbol: str, dates: list[str], base_price: float = 6.0) -> pd.DataFrame:
    """Build a minimal kline df matching get_price_history_df output schema."""
    n = len(dates)
    return pd.DataFrame({
        "symbol": [symbol] * n,
        "adjust_flag": ["qfq"] * n,
        "date": pd.to_datetime(dates),
        "open": [base_price] * n,
        "high": [base_price + 0.5] * n,
        "low": [base_price - 0.2] * n,
        "close": [base_price + 0.2] * n,
        "volume": [100000] * n,
        "amount": [base_price * 100000] * n,
        "amplitude": [10.0] * n,
        "pct_change": [0.02] * n,
        "change_amount": [0.1] * n,
        "turnover": [0.01] * n,
    })


def test_widen_range_trims_back_to_original_window():
    """First fetch returns <120 rows -> widen to 730d; result must be masked
    back to the original [start, end] window the caller requested."""
    original_start = "2026-06-19"
    original_end = "2026-07-18"

    # First call: 20 trading days within the original 1-month window
    first_dates = list(pd.bdate_range("2026-06-19", "2026-07-14").strftime("%Y-%m-%d"))
    df_short = _make_kline_df("601728", first_dates)

    # Second call (widen): ~480 trading days across 2 years
    widen_dates = list(pd.bdate_range("2024-07-18", "2026-07-18").strftime("%Y-%m-%d"))
    df_wide = _make_kline_df("601728", widen_dates)

    with patch.object(api_module, "get_cache_refresh_flag", return_value=False), \
         patch.object(api_module, "get_price_history_df",
                      side_effect=[df_short, df_wide]) as mock_fetch:
        result = api_module.get_price_history("601728", original_start, original_end)

    # Widen must have triggered (two calls)
    assert mock_fetch.call_count == 2

    # Result must be trimmed back to the original window
    assert not result.empty
    assert result["date"].min() >= pd.Timestamp(original_start)
    assert result["date"].max() <= pd.Timestamp(original_end)
    # 1 month of trading days is ~22, definitely not 480+
    assert len(result) < 60, f"expected trimmed result, got {len(result)} rows"


def test_no_widen_when_enough_data():
    """When first fetch returns >=120 rows, widen must NOT trigger and the
    result must not be trimmed (caller gets exactly what was fetched)."""
    original_start = "2025-10-01"
    original_end = "2026-07-18"

    enough_dates = list(pd.bdate_range(original_start, original_end).strftime("%Y-%m-%d"))
    assert len(enough_dates) >= 120, "fixture should have enough rows"
    df_enough = _make_kline_df("601728", enough_dates)

    with patch.object(api_module, "get_cache_refresh_flag", return_value=False), \
         patch.object(api_module, "get_price_history_df",
                      return_value=df_enough) as mock_fetch:
        result = api_module.get_price_history("601728", original_start, original_end)

    # No widen -> only one fetch
    assert mock_fetch.call_count == 1
    # No trimming -> all rows returned
    assert len(result) == len(df_enough)
