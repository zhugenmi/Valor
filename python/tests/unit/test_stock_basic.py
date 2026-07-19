"""Unit tests for stock_basic.get_stock_name caching."""

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from valor.adapters.data import akshare_cache
from valor.tools import stock_basic


@pytest.fixture
def isolated_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Replace module-level `cache` with one backed by tmp_path."""
    from valor.adapters.data.sqlite_cache import AkshareSQLiteCache

    fake = AkshareSQLiteCache(database_path=tmp_path / "test.db")
    monkeypatch.setattr(akshare_cache, "cache", fake)
    monkeypatch.setattr(stock_basic, "cache", fake)


def _make_spot_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "代码": ["600519", "000001", "300750"],
            "名称": ["贵州茅台", "平安银行", "宁德时代"],
        }
    )


def test_get_stock_name_cache_miss_then_hit(
    isolated_cache: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """首次调用触发远程拉取，第二次命中缓存不调远程。"""
    call_count = 0

    def fake_spot() -> pd.DataFrame:
        nonlocal call_count
        call_count += 1
        return _make_spot_df()

    monkeypatch.setattr(stock_basic.ak, "stock_zh_a_spot_em", fake_spot)

    name1 = stock_basic.get_stock_name("600519")
    assert name1 == "贵州茅台"
    assert call_count == 1

    # 第二次应命中缓存，不再调远程
    name2 = stock_basic.get_stock_name("600519")
    assert name2 == "贵州茅台"
    assert call_count == 1


def test_get_stock_name_writes_full_market_to_cache(
    isolated_cache: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """首次拉取应把全市场（不只目标股票）写入缓存，下次查其他股票也命中。"""
    monkeypatch.setattr(stock_basic.ak, "stock_zh_a_spot_em", lambda: _make_spot_df())

    stock_basic.get_stock_name("600519")

    # 查另一只股票应直接命中缓存，不调远程
    remote_called = False

    def fail_if_called() -> pd.DataFrame:
        nonlocal remote_called
        remote_called = True
        return pd.DataFrame()

    monkeypatch.setattr(stock_basic.ak, "stock_zh_a_spot_em", fail_if_called)
    name = stock_basic.get_stock_name("000001")
    assert name == "平安银行"
    assert remote_called is False


def test_get_stock_name_remote_failure_returns_none(
    isolated_cache: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """远程失败 -> 返回 None。"""
    def boom() -> pd.DataFrame:
        raise RuntimeError("network down")

    monkeypatch.setattr(stock_basic.ak, "stock_zh_a_spot_em", boom)
    assert stock_basic.get_stock_name("600519") is None


def test_get_stock_name_empty_symbol(isolated_cache: None) -> None:
    """空 symbol -> 远程拉不到对应行 -> 返回 None（但不抛异常）。"""
    from valor.tools.stock_basic import get_stock_name

    # 不调远程也行：直接预置缓存
    from valor.adapters.data.akshare_cache import cache, COL_CODE, COL_NAME

    cache.upsert_records(
        stock_basic.STOCK_BASIC_TABLE,
        [{COL_CODE: "600519", COL_NAME: "贵州茅台"}],
        key_columns=[COL_CODE],
    )
    # 查一个缓存里没有的 symbol -> 触发远程（mock 成空表）-> 返回 None
    import valor.tools.stock_basic as sb

    with patch.object(sb.ak, "stock_zh_a_spot_em", return_value=pd.DataFrame()):
        assert sb.get_stock_name("999999") is None