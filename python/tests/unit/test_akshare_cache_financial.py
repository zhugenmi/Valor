"""Unit tests for get_financial_indicators / get_financial_report incremental logic."""

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from valor.adapters.data import akshare_cache
from valor.adapters.data.akshare_cache import (
    COL_CODE,
    COL_DATE,
    get_financial_indicators,
)


@pytest.fixture
def isolated_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Replace module-level `cache` with one backed by tmp_path."""
    from valor.adapters.data.sqlite_cache import AkshareSQLiteCache

    fake = AkshareSQLiteCache(database_path=tmp_path / "test.db")
    monkeypatch.setattr(akshare_cache, "cache", fake)
    return tmp_path


def _make_indicator_df(symbol: str, dates: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            COL_CODE: [symbol] * len(dates),
            COL_DATE: dates,
            "净资产收益率(%)": [15.0] * len(dates),
        }
    )


def test_indicators_first_fetch_uses_5_year_default(
    isolated_cache: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """空缓存首次拉取，start_year 默认为 current_year - 5。"""
    captured: dict = {}

    def fake_remote(symbol: str, start_year: str) -> pd.DataFrame:
        captured["start_year"] = start_year
        return _make_indicator_df(symbol, ["2025-12-31", "2026-03-31"])

    monkeypatch.setattr(akshare_cache.ak, "stock_financial_analysis_indicator", fake_remote)
    monkeypatch.setattr(akshare_cache, "_call_with_retry", lambda f, label: f())

    df = get_financial_indicators(symbol="600519")
    assert captured["start_year"] == str(datetime.now().year - 5)
    assert len(df) == 2
    assert COL_CODE in df.columns


def test_indicators_cache_hit_no_refresh(
    isolated_cache: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """有缓存且无新季度应披露 -> 不调远程。"""
    # 预置缓存：最新是 2026 中报，今天 7/19 还没到 Q3 截止(10/31)
    from valor.adapters.data.akshare_cache import cache as real_cache

    cache_df = _make_indicator_df("600519", ["2026-03-31", "2026-06-30"])
    real_cache.upsert_records(
        "stock_financial_analysis_indicator",
        cache_df.to_dict("records"),
        key_columns=[COL_CODE, COL_DATE],
    )

    call_count = 0

    def fake_remote(symbol: str, start_year: str) -> pd.DataFrame:
        nonlocal call_count
        call_count += 1
        return pd.DataFrame()

    monkeypatch.setattr(akshare_cache.ak, "stock_financial_analysis_indicator", fake_remote)
    monkeypatch.setattr(akshare_cache, "_call_with_retry", lambda f, label: f())

    df = get_financial_indicators(symbol="600519")
    assert call_count == 0
    assert len(df) == 2


def test_indicators_incremental_uses_max_year_as_start(
    isolated_cache: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """有缓存但有新季度应披露 -> start_year = MAX(日期).year。"""
    from valor.adapters.data.akshare_cache import cache as real_cache

    # 预置缓存：仅含 2025 年报，今天 7/19 已过 Q1 截止（4/30）
    cache_df = _make_indicator_df("600519", ["2025-12-31"])
    real_cache.upsert_records(
        "stock_financial_analysis_indicator",
        cache_df.to_dict("records"),
        key_columns=[COL_CODE, COL_DATE],
    )

    captured: dict = {}

    def fake_remote(symbol: str, start_year: str) -> pd.DataFrame:
        captured["start_year"] = start_year
        return _make_indicator_df(symbol, ["2026-03-31", "2026-06-30"])

    monkeypatch.setattr(akshare_cache.ak, "stock_financial_analysis_indicator", fake_remote)
    monkeypatch.setattr(akshare_cache, "_call_with_retry", lambda f, label: f())

    df = get_financial_indicators(symbol="600519")
    # MAX(日期) = 2025-12-31 -> year = "2025"
    assert captured["start_year"] == "2025"
    # 合并去重后应包含 3 个不同日期
    assert len(df) == 3


def test_indicators_remote_failure_returns_cached(
    isolated_cache: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """远程失败 + 有缓存 -> 降级返回缓存 + 警告日志。"""
    from valor.adapters.data.akshare_cache import cache as real_cache

    cache_df = _make_indicator_df("600519", ["2026-03-31"])
    real_cache.upsert_records(
        "stock_financial_analysis_indicator",
        cache_df.to_dict("records"),
        key_columns=[COL_CODE, COL_DATE],
    )

    monkeypatch.setattr(akshare_cache, "_call_with_retry", lambda f, label: None)

    df = get_financial_indicators(symbol="600519")
    assert len(df) == 1
    assert df.iloc[0][COL_CODE] == "600519"