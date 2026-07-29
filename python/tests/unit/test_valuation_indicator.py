"""Tests for get_dividend_yield dividend yield calculator.

Verifies the function:
  - Calls stock_history_dividend_detail (Sina) on cache miss
  - Sums 派息 values for 除权除息日 within the last 365 days
  - Converts 每10股派息 to per-share dividend (÷10)
  - Divides by current_price to get yield
"""

from unittest.mock import patch

import akshare as ak
import pandas as pd
import pytest

from valor.adapters.data.akshare_cache import get_dividend_yield


@pytest.fixture(autouse=True)
def _clear_failure_cache():
    """Clear in-memory failure cache between tests to avoid cross-test pollution."""
    from valor.adapters.data import akshare_cache
    akshare_cache._failure_cache.clear()
    yield
    akshare_cache._failure_cache.clear()


def _make_dividend_df() -> pd.DataFrame:
    """Build a fake dividend detail df covering 4 events across 2 years."""
    return pd.DataFrame({
        "公告日期": ["2026-07-10", "2025-12-11", "2025-07-12", "2025-01-16", "2024-11-29"],
        "送股": [0, 0, 0, 0, 0],
        "转增": [0, 0, 0, 0, 0],
        "派息": [25.7969, 25.7800, 31.6900, 25.7600, 25.7600],
        "进度": ["实施", "实施", "实施", "实施", "预案"],
        "除权除息日": ["2026-07-16", "2025-12-18", "2025-07-18", "2025-01-23", pd.NaT],
        "股权登记日": ["2026-07-15", "2025-12-17", "2025-07-17", "2025-01-22", pd.NaT],
        "红股上市日": [pd.NaT, pd.NaT, pd.NaT, pd.NaT, pd.NaT],
    })


def test_get_dividend_yield_sums_recent_12_months_dividends() -> None:
    """以最近除权除息日为锚,过去 365 天内的派息应被累加,÷10 得每股分红,÷股价得股息率。

    五粮液 000858(以 2026-07-16 为最近除权除息日,365 天窗口 [2025-07-16, 2026-07-16]):
      2026-07-16: 25.7969  (本财年年度分红,7 月)
      2025-12-18: 25.7800  (本财年中期分红,12 月)
      2025-07-18: 31.6900  (上财年年度分红,7 月,同月份应被排除)
    合计 51.5769 元/10股 = 5.15769 元/股
    股价 74.3 元,股息率 ≈ 6.94%
    """
    fake_df = _make_dividend_df()

    with patch.object(ak, "stock_history_dividend_detail", return_value=fake_df), \
         patch(
             "valor.adapters.data.akshare_cache.cache.fetch_records",
             return_value=[],
         ), \
         patch(
             "valor.adapters.data.akshare_cache.cache.upsert_records",
         ):
        yield_val = get_dividend_yield("000858", current_price=74.3)

    expected = (25.7969 + 25.7800) / 10 / 74.3
    assert abs(yield_val - expected) < 1e-6
    # 约 6.94%
    assert 0.068 < yield_val < 0.071


def test_get_dividend_yield_returns_zero_when_price_le_zero() -> None:
    """current_price <= 0 应返回 0.0,不调用任何接口."""
    with patch.object(ak, "stock_history_dividend_detail", side_effect=AssertionError("should not call")):
        assert get_dividend_yield("000858", current_price=0.0) == 0.0
        assert get_dividend_yield("000858", current_price=-1.0) == 0.0


def test_get_dividend_yield_returns_zero_on_endpoint_failure() -> None:
    """接口异常应返回 0.0."""
    with patch.object(ak, "stock_history_dividend_detail", side_effect=ConnectionError("blocked")), \
         patch(
             "valor.adapters.data.akshare_cache.cache.fetch_records",
             return_value=[],
         ):
        assert get_dividend_yield("000858", current_price=74.3) == 0.0


def test_get_dividend_yield_returns_zero_when_no_valid_announce_date() -> None:
    """所有分红记录的公告日期为 NaT 时返回 0.0.

    预案(除权除息日 NaT 但公告日期有效)现在会被算入股息率,
    所以"全 NaT 除权除息日"不再意味着返回 0.0; 改为校验公告日期无效。
    """
    all_nat_df = pd.DataFrame({
        "公告日期": [pd.NaT],
        "送股": [0],
        "转增": [0],
        "派息": [10.0],
        "进度": ["预案"],
        "除权除息日": [pd.NaT],
        "股权登记日": [pd.NaT],
        "红股上市日": [pd.NaT],
    })

    with patch.object(ak, "stock_history_dividend_detail", return_value=all_nat_df), \
         patch(
             "valor.adapters.data.akshare_cache.cache.fetch_records",
             return_value=[],
         ), \
         patch(
             "valor.adapters.data.akshare_cache.cache.upsert_records",
         ):
        assert get_dividend_yield("000858", current_price=74.3) == 0.0


def test_get_dividend_yield_uses_cache_when_available() -> None:
    """缓存命中不应触发 akshare 调用."""
    cached_records = [
        {
            "代码": "000858",
            "公告日期": "2026-07-10",
            "派息": 25.7969,
            "除权除息日": "2026-07-16",
        },
        {
            "代码": "000858",
            "公告日期": "2025-12-11",
            "派息": 25.7800,
            "除权除息日": "2025-12-18",
        },
    ]

    with patch.object(ak, "stock_history_dividend_detail", side_effect=AssertionError("should not call")), \
         patch(
             "valor.adapters.data.akshare_cache.cache.fetch_records",
             return_value=cached_records,
         ):
        yield_val = get_dividend_yield("000858", current_price=74.3)

    expected = (25.7969 + 25.7800) / 10 / 74.3
    assert abs(yield_val - expected) < 1e-6
