"""Tests for _fetch_realtime_market_cap market cap fetcher.

Verifies the function uses stock_zh_valuation_baidu (single-ticker, lightweight)
instead of stock_zh_a_spot_em (full-market scan, frequently blocked), and
converts the value from 亿元 to yuan.
"""

from unittest.mock import patch

import akshare as ak
import pandas as pd

from valor.tools.api import _fetch_realtime_market_cap


def test_fetch_market_cap_uses_valuation_baidu_endpoint() -> None:
    """_fetch_realtime_market_cap calls stock_zh_valuation_baidu, not stock_zh_a_spot_em."""
    endpoint_calls: list[str] = []

    def fake_valuation_baidu(symbol: str, indicator: str, period: str) -> pd.DataFrame:
        endpoint_calls.append(f"stock_zh_valuation_baidu:{symbol}")
        return pd.DataFrame(
            {"date": ["2026-07-15", "2026-07-16"], "value": [2363.43, 2241.18]}
        )

    def fail_spot_em() -> pd.DataFrame:
        endpoint_calls.append("stock_zh_a_spot_em")
        raise AssertionError("stock_zh_a_spot_em must not be called")

    with patch.object(ak, "stock_zh_valuation_baidu", fake_valuation_baidu), \
         patch.object(ak, "stock_zh_a_spot_em", fail_spot_em):
        result = _fetch_realtime_market_cap("000725")

    assert "stock_zh_valuation_baidu:000725" in endpoint_calls
    assert "stock_zh_a_spot_em" not in endpoint_calls
    # 2241.18 亿元 -> 224,118,000,000 yuan
    assert result == 2241.18 * 1e8


def test_fetch_market_cap_returns_zero_on_endpoint_failure() -> None:
    """When the endpoint raises, the function returns 0.0 (graceful fallback)."""
    with patch.object(ak, "stock_zh_valuation_baidu", side_effect=ConnectionError("blocked")), \
         patch.object(ak, "stock_zh_a_spot_em", side_effect=AssertionError):
        result = _fetch_realtime_market_cap("000725")

    assert result == 0.0


def test_fetch_market_cap_returns_zero_on_empty_dataframe() -> None:
    """Empty valuation dataframe yields 0.0 (no data available)."""
    with patch.object(ak, "stock_zh_valuation_baidu", return_value=pd.DataFrame()), \
         patch.object(ak, "stock_zh_a_spot_em", side_effect=AssertionError):
        result = _fetch_realtime_market_cap("000725")

    assert result == 0.0
