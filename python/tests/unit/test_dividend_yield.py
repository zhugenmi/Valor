"""Unit tests for get_dividend_yield (TTM) and get_latest_dividend_detail.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
from pathlib import Path

import pandas as pd
import pytest

from valor.adapters.data import akshare_cache
from valor.adapters.data.akshare_cache import (
    get_dividend_yield,
    get_latest_dividend_detail,
)


@pytest.fixture
def isolated_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from valor.adapters.data.sqlite_cache import AkshareSQLiteCache
    fake = AkshareSQLiteCache(database_path=tmp_path / "test_dividend.db")
    monkeypatch.setattr(akshare_cache, "cache", fake)


def _make_dividend_df(records: list[dict]) -> pd.DataFrame:
    """Build a dividend detail DataFrame mimicking akshare format."""
    return pd.DataFrame(records)


def test_dividend_yield_ttm_sums_recent_365_days(
    isolated_cache: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TTM 口径：以最近公告日为锚，过去 365 天内的分红合计 / 股价。

    模拟 601728 场景：最近公告日 now-50，365 天内还有一次(now-330)，
    365 天外一次(now-430，相对 now-50 是 380 天前)。
    期望 (0.908+1.812)/10/6.24 ≈ 4.36%。
    """
    now = pd.Timestamp.now()
    records = [
        {"公告日期": (now - pd.Timedelta(days=50)).strftime("%Y-%m-%d"),
         "送股": 0, "转增": 0, "派息": 0.908, "进度": "实施",
         "除权除息日": (now - pd.Timedelta(days=45)).strftime("%Y-%m-%d"),
         "股权登记日": "", "红股上市日": ""},
        {"公告日期": (now - pd.Timedelta(days=330)).strftime("%Y-%m-%d"),
         "送股": 0, "转增": 0, "派息": 1.812, "进度": "实施",
         "除权除息日": (now - pd.Timedelta(days=320)).strftime("%Y-%m-%d"),
         "股权登记日": "", "红股上市日": ""},
        {"公告日期": (now - pd.Timedelta(days=430)).strftime("%Y-%m-%d"),
         "送股": 0, "转增": 0, "派息": 0.927, "进度": "实施",
         "除权除息日": (now - pd.Timedelta(days=420)).strftime("%Y-%m-%d"),
         "股权登记日": "", "红股上市日": ""},
    ]
    monkeypatch.setattr(
        akshare_cache.ak, "stock_history_dividend_detail",
        lambda symbol, indicator: _make_dividend_df(records),
    )

    y = get_dividend_yield("601728", 6.24)
    assert 0.043 < y < 0.044, f"TTM 股息率应 ~4.36%, 实际 {y*100:.2f}%"


def test_dividend_yield_includes_pending_proposal(
    isolated_cache: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """最近一个财年的股息率应包括预案(尚未实施的年报分红)。

    回归场景：海尔智家 600690 在 2026-07-29 测试。
      2025 年报预案:   公告 90 天前,  10派8.867  (尚未实施, 除权除息日 NaT)
      2025 半年报实施: 公告 270 天前, 10派2.692  (派息日 2025-11-07)
      2024 年报实施:   公告 455 天前, 10派9.6504 (同月份, 应排除)

    窗口以最新公告日(90 天前)为锚、往前 365 天, 2024 年报公告恰好落在边界,
    但同月份(4 月)应被排除。期望 (8.867 + 2.692) / 10 / 22.40 ≈ 5.16%。
    旧实现过滤掉 NaT 除权除息日的预案, 只取 2024 年报 + 2025 半年报 = 5.51%,
    把上一年年报当成当前财年, 错误。
    """
    now = pd.Timestamp.now()
    records = [
        # 2025 年报预案: 90 天前公告（最近）
        {"公告日期": (now - pd.Timedelta(days=90)).strftime("%Y-%m-%d"),
         "送股": 0, "转增": 0, "派息": 8.867, "进度": "预案",
         "除权除息日": "", "股权登记日": "", "红股上市日": ""},
        # 2025 半年报实施: 270 天前公告
        {"公告日期": (now - pd.Timedelta(days=270)).strftime("%Y-%m-%d"),
         "送股": 0, "转增": 0, "派息": 2.692, "进度": "实施",
         "除权除息日": (now - pd.Timedelta(days=260)).strftime("%Y-%m-%d"),
         "股权登记日": "", "红股上市日": ""},
        # 2024 年报实施: 455 天前公告（同月份, 排除）
        {"公告日期": (now - pd.Timedelta(days=455)).strftime("%Y-%m-%d"),
         "送股": 0, "转增": 0, "派息": 9.6504, "进度": "实施",
         "除权除息日": (now - pd.Timedelta(days=400)).strftime("%Y-%m-%d"),
         "股权登记日": "", "红股上市日": ""},
    ]
    monkeypatch.setattr(
        akshare_cache.ak, "stock_history_dividend_detail",
        lambda symbol, indicator: _make_dividend_df(records),
    )

    y = get_dividend_yield("600690", 22.40)
    assert 0.050 < y < 0.053, f"股息率应 ~5.16% (含预案), 实际 {y*100:.2f}%"


def test_dividend_yield_takes_only_latest_two_records(
    isolated_cache: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """只取最新 2 条分红记录，第 3、4 条（更早的）不被算入。

    回归场景：五粮液 000858 在 2026-07-29 测试。
      work[0] = now-13  公告 (25.7969, 7 月年度分红)
      work[1] = now-223 公告 (25.78, 12 月中期分红), 间隔 210 天 < 365, 月份不同 -> 取
      work[2] = now-376 公告 (31.69, 7 月上一年年度), 不取（只取最新 2 条）
      work[3] = now-552 公告 (25.76, 1 月), 不取

    期望 (25.7969 + 25.78) / 10 / 74.8 ≈ 6.90%。
    """
    now = pd.Timestamp.now()
    records = [
        # 最近年度分红: 13 天前（7 月）
        {"公告日期": (now - pd.Timedelta(days=20)).strftime("%Y-%m-%d"),
         "送股": 0, "转增": 0, "派息": 25.7969, "进度": "实施",
         "除权除息日": (now - pd.Timedelta(days=13)).strftime("%Y-%m-%d"),
         "股权登记日": "", "红股上市日": ""},
        # 本财年中期分红: 223 天前（12 月）
        {"公告日期": (now - pd.Timedelta(days=230)).strftime("%Y-%m-%d"),
         "送股": 0, "转增": 0, "派息": 25.7800, "进度": "实施",
         "除权除息日": (now - pd.Timedelta(days=223)).strftime("%Y-%m-%d"),
         "股权登记日": "", "红股上市日": ""},
        # 上一年年度分红: 376 天前（7 月，只取最新 2 条，不取）
        {"公告日期": (now - pd.Timedelta(days=385)).strftime("%Y-%m-%d"),
         "送股": 0, "转增": 0, "派息": 31.6900, "进度": "实施",
         "除权除息日": (now - pd.Timedelta(days=376)).strftime("%Y-%m-%d"),
         "股权登记日": "", "红股上市日": ""},
        # 上一年中期分红: 552 天前（1 月，不取）
        {"公告日期": (now - pd.Timedelta(days=560)).strftime("%Y-%m-%d"),
         "送股": 0, "转增": 0, "派息": 25.7600, "进度": "实施",
         "除权除息日": (now - pd.Timedelta(days=552)).strftime("%Y-%m-%d"),
         "股权登记日": "", "红股上市日": ""},
    ]
    monkeypatch.setattr(
        akshare_cache.ak, "stock_history_dividend_detail",
        lambda symbol, indicator: _make_dividend_df(records),
    )

    # (25.7969 + 25.7800) / 10 / 74.8 ≈ 6.90%
    y = get_dividend_yield("000858", 74.8)
    assert 0.068 < y < 0.070, f"TTM 股息率应 ~6.90%, 实际 {y*100:.2f}%"


def test_dividend_yield_skips_records_beyond_365_day_gap(
    isolated_cache: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """第 2 条与最新 1 条间隔 >= 365 天时不取（只取最新 1 条）。"""
    now = pd.Timestamp.now()
    records = [
        # 最新分红: now-100
        {"公告日期": (now - pd.Timedelta(days=90)).strftime("%Y-%m-%d"),
         "送股": 0, "转增": 0, "派息": 1.0, "进度": "实施",
         "除权除息日": (now - pd.Timedelta(days=100)).strftime("%Y-%m-%d"),
         "股权登记日": "", "红股上市日": ""},
        # 相对 now-100 是 500 天前（>=365 天），不取
        {"公告日期": (now - pd.Timedelta(days=590)).strftime("%Y-%m-%d"),
         "送股": 0, "转增": 0, "派息": 5.0, "进度": "实施",
         "除权除息日": (now - pd.Timedelta(days=600)).strftime("%Y-%m-%d"),
         "股权登记日": "", "红股上市日": ""},
    ]
    monkeypatch.setattr(
        akshare_cache.ak, "stock_history_dividend_detail",
        lambda symbol, indicator: _make_dividend_df(records),
    )
    # 只取最近一次: 1.0/10/10 = 0.01
    assert get_dividend_yield("600000", 10.0) == 0.01


def test_dividend_yield_zero_price_returns_zero(
    isolated_cache: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert get_dividend_yield("600000", 0.0) == 0.0


def test_dividend_yield_no_records_returns_zero(
    isolated_cache: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        akshare_cache.ak, "stock_history_dividend_detail",
        lambda symbol, indicator: pd.DataFrame(),
    )
    assert get_dividend_yield("600000", 10.0) == 0.0


def test_latest_dividend_detail_returns_most_recent(
    isolated_cache: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """get_latest_dividend_detail 返回除权除息日最近的一条。"""
    now = pd.Timestamp.now()
    records = [
        {"公告日期": (now - pd.Timedelta(days=50)).strftime("%Y-%m-%d"),
         "送股": 0, "转增": 0, "派息": 0.908, "进度": "实施",
         "除权除息日": (now - pd.Timedelta(days=45)).strftime("%Y-%m-%d"),
         "股权登记日": "", "红股上市日": ""},
        {"公告日期": (now - pd.Timedelta(days=330)).strftime("%Y-%m-%d"),
         "送股": 0, "转增": 0, "派息": 1.812, "进度": "实施",
         "除权除息日": (now - pd.Timedelta(days=320)).strftime("%Y-%m-%d"),
         "股权登记日": "", "红股上市日": ""},
    ]
    monkeypatch.setattr(
        akshare_cache.ak, "stock_history_dividend_detail",
        lambda symbol, indicator: _make_dividend_df(records),
    )

    # 先调 get_dividend_yield 填充缓存
    get_dividend_yield("601728", 6.24)
    detail = get_latest_dividend_detail("601728")
    assert detail is not None
    assert detail["派息"] == 0.908  # 最近一条（除权除息日最新）
    assert detail["进度"] == "实施"


def test_latest_dividend_detail_excludes_pending_proposal(
    isolated_cache: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """除权除息日为 NaT 的预案记录被排除，返回最近一次已实施分红。"""
    now = pd.Timestamp.now()
    records = [
        # 预案: 除权除息日为空（最新公告，但尚未实施）
        {"公告日期": (now - pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
         "送股": 0, "转增": 0, "派息": 9.999, "进度": "预案",
         "除权除息日": "", "股权登记日": "", "红股上市日": ""},
        # 已实施: 45 天前
        {"公告日期": (now - pd.Timedelta(days=50)).strftime("%Y-%m-%d"),
         "送股": 0, "转增": 0, "派息": 0.908, "进度": "实施",
         "除权除息日": (now - pd.Timedelta(days=45)).strftime("%Y-%m-%d"),
         "股权登记日": "", "红股上市日": ""},
    ]
    monkeypatch.setattr(
        akshare_cache.ak, "stock_history_dividend_detail",
        lambda symbol, indicator: _make_dividend_df(records),
    )

    get_dividend_yield("601728", 6.24)  # 填充缓存
    detail = get_latest_dividend_detail("601728")
    assert detail is not None
    assert detail["派息"] == 0.908
    assert detail["进度"] == "实施"


def test_latest_dividend_detail_none_on_empty(
    isolated_cache: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        akshare_cache.ak, "stock_history_dividend_detail",
        lambda symbol, indicator: pd.DataFrame(),
    )
    assert get_latest_dividend_detail("600000") is None
