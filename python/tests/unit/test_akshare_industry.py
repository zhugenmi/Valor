"""Unit tests for get_stock_industry.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
from pathlib import Path

import pandas as pd
import pytest

from valor.adapters.data import akshare_cache
from valor.adapters.data.akshare_cache import get_stock_industry


@pytest.fixture
def isolated_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from valor.adapters.data.sqlite_cache import AkshareSQLiteCache
    fake = AkshareSQLiteCache(database_path=tmp_path / "test_industry.db")
    monkeypatch.setattr(akshare_cache, "cache", fake)


def _make_spot_df_with_industry() -> pd.DataFrame:
    return pd.DataFrame({
        "代码": ["600036", "600519", "000001"],
        "名称": ["招商银行", "贵州茅台", "平安银行"],
        "行业": ["银行", "食品饮料", "银行"],
    })


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