"""Unit tests for get_stock_spot_row realtime quote fetcher.

Verifies the function uses the lightweight stock_bid_ask_em endpoint
(single-ticker) instead of stock_zh_a_spot_em (full-market scan, ~5000 rows),
which is frequently blocked by East Money's anti-scraping measures.
"""

from pathlib import Path
from unittest.mock import patch

import akshare as ak
import pandas as pd
import pytest

from valor.adapters.data import akshare_cache
from valor.adapters.data.sqlite_cache import AkshareSQLiteCache


@pytest.fixture
def temp_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AkshareSQLiteCache:
    """Replace the module-level cache with a temp SQLite cache."""
    cache = AkshareSQLiteCache(tmp_path / "test.db")
    monkeypatch.setattr(akshare_cache, "cache", cache)
    return cache


def _fake_bid_ask_df() -> pd.DataFrame:
    """Sample stock_bid_ask_em output shaped like the real endpoint."""
    return pd.DataFrame(
        {
            "item": [
                "最新", "均价", "涨幅", "涨跌", "总手", "金额", "换手", "量比",
            ],
            "value": [
                6.14, 6.06, 1.49, 0.09, 24780680, 15017980000, 7.01, 0.96,
            ],
        }
    )


def test_get_stock_spot_row_uses_bid_ask_endpoint(temp_cache: AkshareSQLiteCache) -> None:
    """get_stock_spot_row calls stock_bid_ask_em(symbol=), not stock_zh_a_spot_em()."""
    endpoint_calls: list[str] = []

    def fake_bid_ask(symbol: str) -> pd.DataFrame:
        endpoint_calls.append(f"stock_bid_ask_em:{symbol}")
        return _fake_bid_ask_df()

    def fail_spot_em() -> pd.DataFrame:
        endpoint_calls.append("stock_zh_a_spot_em")
        raise AssertionError("stock_zh_a_spot_em must not be called")

    with patch.object(ak, "stock_bid_ask_em", fake_bid_ask), \
         patch.object(ak, "stock_zh_a_spot_em", fail_spot_em):
        result = akshare_cache.get_stock_spot_row("000725")

    assert result is not None
    assert "stock_bid_ask_em:000725" in endpoint_calls
    assert "stock_zh_a_spot_em" not in endpoint_calls


def test_get_stock_spot_row_returns_expected_fields(temp_cache: AkshareSQLiteCache) -> None:
    """Returned Series carries ticker code and key realtime fields."""
    with patch.object(ak, "stock_bid_ask_em", return_value=_fake_bid_ask_df()), \
         patch.object(ak, "stock_zh_a_spot_em", side_effect=AssertionError):
        result = akshare_cache.get_stock_spot_row("000725")

    assert result is not None
    assert result["代码"] == "000725"
    assert result["最新价"] == 6.14
    assert result["涨跌幅"] == 1.49
    assert result["成交量"] == 24780680
    assert result["成交额"] == 15017980000


def test_get_stock_spot_row_caches_result(temp_cache: AkshareSQLiteCache) -> None:
    """Second call within TTL hits cache; endpoint is called only once."""
    call_count = 0

    def counting_bid_ask(symbol: str) -> pd.DataFrame:
        nonlocal call_count
        call_count += 1
        return _fake_bid_ask_df()

    with patch.object(ak, "stock_bid_ask_em", counting_bid_ask), \
         patch.object(ak, "stock_zh_a_spot_em", side_effect=AssertionError):
        first = akshare_cache.get_stock_spot_row("000725")
        second = akshare_cache.get_stock_spot_row("000725")

    assert call_count == 1
    assert first is not None and second is not None
    assert first["代码"] == second["代码"]
    assert first["最新价"] == second["最新价"]


def test_get_stock_spot_row_returns_none_on_endpoint_failure(
    temp_cache: AkshareSQLiteCache,
) -> None:
    """When the endpoint raises, the function returns None (graceful degradation)."""
    with patch.object(ak, "stock_bid_ask_em", side_effect=ConnectionError("blocked")), \
         patch.object(ak, "stock_zh_a_spot_em", side_effect=AssertionError):
        result = akshare_cache.get_stock_spot_row("000725")

    assert result is None
