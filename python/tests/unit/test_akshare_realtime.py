"""Unit tests for realtime quote fetcher and stock industry resolution.

Verifies get_stock_spot_row uses the lightweight stock_bid_ask_em endpoint
(single-ticker) instead of stock_zh_a_spot_em (full-market scan, ~5000 rows),
which is frequently blocked by East Money's anti-scraping measures, and that
get_stock_industry caches its full-market snapshot.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from pathlib import Path
from unittest.mock import patch

import akshare as ak
import pandas as pd
import pytest

from valor.adapters.data import akshare_cache
from valor.adapters.data.akshare_cache import get_stock_industry
from valor.adapters.data.sqlite_cache import AkshareSQLiteCache


@pytest.fixture
def temp_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AkshareSQLiteCache:
    """Replace the module-level cache with a temp SQLite cache."""
    cache = AkshareSQLiteCache(tmp_path / "test.db")
    monkeypatch.setattr(akshare_cache, "cache", cache)
    return cache


@pytest.fixture
def isolated_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from valor.adapters.data.sqlite_cache import AkshareSQLiteCache
    fake = AkshareSQLiteCache(database_path=tmp_path / "test_industry.db")
    monkeypatch.setattr(akshare_cache, "cache", fake)


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


def _make_spot_df_with_industry() -> pd.DataFrame:
    return pd.DataFrame({
        "代码": ["600036", "600519", "000001"],
        "名称": ["招商银行", "贵州茅台", "平安银行"],
        "行业": ["银行", "食品饮料", "银行"],
    })


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
         patch.object(ak, "stock_zh_a_spot_em", fail_spot_em), \
         patch("valor.adapters.data.akshare_cache.is_market_open", return_value=True):
        result = akshare_cache.get_stock_spot_row("000725")

    assert result is not None
    assert "stock_bid_ask_em:000725" in endpoint_calls
    assert "stock_zh_a_spot_em" not in endpoint_calls


def test_get_stock_spot_row_returns_expected_fields(temp_cache: AkshareSQLiteCache) -> None:
    """Returned Series carries ticker code and key realtime fields."""
    with patch.object(ak, "stock_bid_ask_em", return_value=_fake_bid_ask_df()), \
         patch.object(ak, "stock_zh_a_spot_em", side_effect=AssertionError), \
         patch("valor.adapters.data.akshare_cache.is_market_open", return_value=True):
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
         patch.object(ak, "stock_zh_a_spot_em", side_effect=AssertionError), \
         patch("valor.adapters.data.akshare_cache.is_market_open", return_value=True):
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


def test_get_stock_industry_cache_miss_then_hit(
    isolated_cache: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    call_count = 0

    def fake_spot() -> pd.DataFrame:
        nonlocal call_count
        call_count += 1
        return _make_spot_df_with_industry()

    monkeypatch.setattr(akshare_cache, "ak", type("F", (), {"stock_zh_a_spot_em": fake_spot}))

    industry = get_stock_industry("600036")
    assert industry == "银行"
    assert call_count == 1

    # 第二次命中缓存
    industry2 = get_stock_industry("600036")
    assert industry2 == "银行"
    assert call_count == 1  # 不再调远程


def test_get_stock_industry_returns_none_on_missing(
    monkeypatch: pytest.MonkeyPatch, isolated_cache: None
) -> None:
    def fake_spot() -> pd.DataFrame:
        return _make_spot_df_with_industry()
    monkeypatch.setattr(akshare_cache, "ak", type("F", (), {"stock_zh_a_spot_em": fake_spot}))
    assert get_stock_industry("999999") is None


def test_get_stock_industry_fallback_to_none_on_exception(
    monkeypatch: pytest.MonkeyPatch, isolated_cache: None
) -> None:
    def boom() -> pd.DataFrame:
        raise RuntimeError("network error")
    monkeypatch.setattr(akshare_cache, "ak", type("F", (), {"stock_zh_a_spot_em": boom}))
    assert get_stock_industry("600036") is None