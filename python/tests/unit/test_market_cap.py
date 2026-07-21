"""Tests for valuation indicator fetcher.

Verifies ``get_valuation_indicator`` calls ``stock_zh_valuation_baidu``
for three indicators (总市值 / 市盈率(TTM) / 市净率), converts market cap
from 亿元 to yuan, and pulls latest close price from cached price history.
"""

from unittest.mock import patch

import akshare as ak
import pandas as pd
import pytest

from valor.adapters.data.akshare_cache import get_valuation_indicator


@pytest.fixture(autouse=True)
def _clear_failure_cache():
    """Clear in-memory failure cache between tests to avoid cross-test pollution."""
    from valor.adapters.data import akshare_cache
    akshare_cache._failure_cache.clear()
    yield
    akshare_cache._failure_cache.clear()


def _make_valuation_df(values: list[float]) -> pd.DataFrame:
    """Build a fake stock_zh_valuation_baidu dataframe."""
    n = len(values)
    return pd.DataFrame({
        "date": pd.date_range("2026-07-01", periods=n, freq="D").strftime("%Y-%m-%d"),
        "value": values,
    })


def test_get_valuation_indicator_calls_three_baidu_endpoints() -> None:
    """Should call stock_zh_valuation_baidu three times: 总市值 / 市盈率(TTM) / 市净率."""
    endpoint_calls: list[str] = []

    def fake_valuation_baidu(symbol: str, indicator: str, period: str) -> pd.DataFrame:
        endpoint_calls.append(f"{symbol}:{indicator}")
        # 总市值 in 亿元; PE-TTM and PB are unitless ratios
        if indicator == "总市值":
            return _make_valuation_df([2800.0, 2887.14])
        if indicator == "市盈率(TTM)":
            return _make_valuation_df([22.5, 22.91])
        if indicator == "市净率":
            return _make_valuation_df([4.4, 4.45])
        return pd.DataFrame()

    fake_price_df = pd.DataFrame({
        "date": pd.to_datetime(["2026-07-20", "2026-07-21"]),
        "close": [74.0, 74.30],
    })

    with patch.object(ak, "stock_zh_valuation_baidu", fake_valuation_baidu), \
         patch(
             "valor.adapters.data.akshare_cache.get_price_history_df",
             return_value=fake_price_df,
         ), \
         patch(
             "valor.adapters.data.akshare_cache.cache.fetch_records",
             return_value=[],
         ), \
         patch(
             "valor.adapters.data.akshare_cache.cache.upsert_records",
         ):
        result = get_valuation_indicator("000858")

    assert "000858:总市值" in endpoint_calls
    assert "000858:市盈率(TTM)" in endpoint_calls
    assert "000858:市净率" in endpoint_calls
    assert result["pe_ttm"] == 22.91
    assert result["pb"] == 4.45
    # 2887.14 亿元 -> 288,714,000,000 yuan
    assert result["market_cap"] == 2887.14 * 1e8
    assert result["price"] == 74.30


def test_get_valuation_indicator_returns_empty_when_any_endpoint_fails() -> None:
    """If any of the three baidu endpoints returns empty, return empty dict."""
    def fail_valuation_baidu(symbol: str, indicator: str, period: str) -> pd.DataFrame:
        if indicator == "市净率":
            return pd.DataFrame()  # PB endpoint fails
        return _make_valuation_df([2800.0, 2887.14])

    with patch.object(ak, "stock_zh_valuation_baidu", fail_valuation_baidu), \
         patch(
             "valor.adapters.data.akshare_cache.cache.fetch_records",
             return_value=[],
         ), \
         patch(
             "valor.adapters.data.akshare_cache.cache.upsert_records",
         ):
        result = get_valuation_indicator("000858")

    assert result == {}


def test_get_valuation_indicator_uses_cache_when_available() -> None:
    """Cache hit should not trigger any akshare calls."""
    cached_record = {
        "代码": "000858",
        "date": "2026-07-21",
        "pe_ttm": 22.91,
        "pb": 4.45,
        "market_cap": 2887.14 * 1e8,
        "price": 74.30,
    }

    with patch.object(ak, "stock_zh_valuation_baidu", side_effect=AssertionError("should not call")), \
         patch(
             "valor.adapters.data.akshare_cache.cache.fetch_records",
             return_value=[cached_record],
         ):
        result = get_valuation_indicator("000858")

    assert result["pe_ttm"] == 22.91
    assert result["market_cap"] == 2887.14 * 1e8
    assert result["price"] == 74.30
