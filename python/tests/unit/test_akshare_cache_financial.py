"""Unit tests for financial indicators, reports, dividends, valuation, and related helpers.

Covers get_financial_indicators / get_financial_report incremental logic,
dividend yield (TTM) and dividend history, valuation indicator, market cap,
history PB percentile, bank special indicators, R&D expense, and stock basic
name caching.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import akshare as ak
import pandas as pd
import pytest

from valor.adapters.data import akshare_cache
from valor.adapters.data.akshare_cache import (
    COL_CODE,
    COL_DATE,
    COL_REPORT_DATE,
    COL_REPORT_TYPE,
    _compute_dividend_years,
    _compute_pb_percentile,
    get_bank_special_indicators,
    get_dividend_history,
    get_dividend_yield,
    get_financial_indicators,
    get_financial_report,
    get_history_pb,
    get_latest_dividend_detail,
    get_r_and_d_expense,
    get_valuation_indicator,
)
from valor.tools import stock_basic


@pytest.fixture
def isolated_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Replace module-level `cache` with one backed by tmp_path."""
    from valor.adapters.data.sqlite_cache import AkshareSQLiteCache

    fake = AkshareSQLiteCache(database_path=tmp_path / "test.db")
    monkeypatch.setattr(akshare_cache, "cache", fake)
    return tmp_path


@pytest.fixture
def _yield_isolated_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from valor.adapters.data.sqlite_cache import AkshareSQLiteCache
    fake = AkshareSQLiteCache(database_path=tmp_path / "test_dividend.db")
    monkeypatch.setattr(akshare_cache, "cache", fake)


@pytest.fixture
def _stock_basic_isolated_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Replace module-level `cache` with one backed by tmp_path."""
    from valor.adapters.data.sqlite_cache import AkshareSQLiteCache

    fake = AkshareSQLiteCache(database_path=tmp_path / "test.db")
    monkeypatch.setattr(akshare_cache, "cache", fake)
    monkeypatch.setattr(stock_basic, "cache", fake)


@pytest.fixture(autouse=True)
def _clear_failure_cache():
    """Clear in-memory failure cache between tests to avoid cross-test pollution."""
    akshare_cache._failure_cache.clear()
    yield
    akshare_cache._failure_cache.clear()


@pytest.fixture(autouse=True)
def _market_cap_clear_failure_cache():
    """Clear in-memory failure cache between tests to avoid cross-test pollution."""
    akshare_cache._failure_cache.clear()
    yield
    akshare_cache._failure_cache.clear()


def _make_indicator_df(symbol: str, dates: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            COL_CODE: [symbol] * len(dates),
            COL_DATE: dates,
            "净资产收益率(%)": [15.0] * len(dates),
        }
    )


def _make_report_df(symbol: str, report_type: str, report_dates: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            COL_CODE: [symbol] * len(report_dates),
            COL_REPORT_TYPE: [report_type] * len(report_dates),
            COL_REPORT_DATE: report_dates,
            "净利润": [1.0] * len(report_dates),
        }
    )


def _make_dividend_df(records: list[dict]) -> pd.DataFrame:
    """Build a dividend detail DataFrame mimicking akshare format."""
    return pd.DataFrame(records)


def _valuation_make_dividend_df() -> pd.DataFrame:
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


def _make_valuation_df(values: list[float]) -> pd.DataFrame:
    """Build a fake stock_zh_valuation_baidu dataframe."""
    n = len(values)
    return pd.DataFrame({
        "date": pd.date_range("2026-07-01", periods=n, freq="D").strftime("%Y-%m-%d"),
        "value": values,
    })


def _make_income_df(rd: float, revenue: float, capitalized: float = 0) -> pd.DataFrame:
    """构造利润表 DataFrame, 模拟 get_financial_report 返回格式."""
    data = {
        "研发费用": [rd],
        "营业总收入": [revenue],
        "报告日": ["2024-12-31"],
    }
    if capitalized > 0:
        data["研发资本化金额"] = [capitalized]
    return pd.DataFrame(data)


def _make_spot_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "代码": ["600519", "000001", "300750"],
            "名称": ["贵州茅台", "平安银行", "宁德时代"],
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

    cache_df = _make_indicator_df("600519", ["2025-12-31"])
    real_cache.upsert_records(
        "stock_financial_analysis_indicator",
        cache_df.to_dict("records"),
        key_columns=[COL_CODE, COL_DATE],
    )

    monkeypatch.setattr(akshare_cache, "_call_with_retry", lambda f, label: None)

    df = get_financial_indicators(symbol="600519")
    assert len(df) == 1
    assert df.iloc[0][COL_CODE] == "600519"
    assert "降级" in caplog.text


def test_report_first_fetch(isolated_cache: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """空缓存首次拉取。"""
    def fake_remote(stock: str, symbol: str) -> pd.DataFrame:
        return _make_report_df("600519", symbol, ["2025-12-31", "2026-03-31"])

    monkeypatch.setattr(akshare_cache.ak, "stock_financial_report_sina", fake_remote)
    monkeypatch.setattr(akshare_cache, "_call_with_retry", lambda f, label: f())

    df = get_financial_report(symbol="600519", report_type="利润表")
    assert len(df) == 2
    assert COL_REPORT_DATE in df.columns


def test_report_cache_hit_no_refresh(
    isolated_cache: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """有缓存且无新季度应披露 -> 不调远程。"""
    from valor.adapters.data.akshare_cache import cache as real_cache

    # 预置缓存：最新 2026 中报(6/30)，今天 7/19，Q3 截止 10/31 还没到
    cache_df = _make_report_df("600519", "利润表", ["2026-03-31", "2026-06-30"])
    real_cache.upsert_records(
        "stock_financial_report_sina",
        cache_df.to_dict("records"),
        key_columns=[COL_CODE, COL_REPORT_TYPE, COL_REPORT_DATE],
    )

    call_count = 0

    def fake_remote(stock: str, symbol: str) -> pd.DataFrame:
        nonlocal call_count
        call_count += 1
        return pd.DataFrame()

    monkeypatch.setattr(akshare_cache.ak, "stock_financial_report_sina", fake_remote)
    monkeypatch.setattr(akshare_cache, "_call_with_retry", lambda f, label: f())

    df = get_financial_report(symbol="600519", report_type="利润表")
    assert call_count == 0
    assert len(df) == 2


def test_report_refresh_when_new_period_due(
    isolated_cache: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """有缓存但有新季度应披露 -> 调远程 + 合并去重。"""
    from valor.adapters.data.akshare_cache import cache as real_cache

    # 预置缓存：最新 2025 年报(12/31)，今天 7/19 已过 Q1 截止(4/30)
    cache_df = _make_report_df("600519", "利润表", ["2025-12-31"])
    real_cache.upsert_records(
        "stock_financial_report_sina",
        cache_df.to_dict("records"),
        key_columns=[COL_CODE, COL_REPORT_TYPE, COL_REPORT_DATE],
    )

    # 远程返回包含旧的 2026-03-31 + 新的 2026-06-30（修订场景）
    def fake_remote(stock: str, symbol: str) -> pd.DataFrame:
        return _make_report_df("600519", symbol, ["2026-03-31", "2026-06-30"])

    monkeypatch.setattr(akshare_cache.ak, "stock_financial_report_sina", fake_remote)
    monkeypatch.setattr(akshare_cache, "_call_with_retry", lambda f, label: f())

    df = get_financial_report(symbol="600519", report_type="利润表")
    # 合并去重后应包含 3 个不同报告日
    assert len(df) == 3


def test_report_remote_failure_returns_cached(
    isolated_cache: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """远程失败 + 有缓存 -> 降级返回缓存。"""
    from valor.adapters.data.akshare_cache import cache as real_cache

    cache_df = _make_report_df("600519", "利润表", ["2026-03-31"])
    real_cache.upsert_records(
        "stock_financial_report_sina",
        cache_df.to_dict("records"),
        key_columns=[COL_CODE, COL_REPORT_TYPE, COL_REPORT_DATE],
    )

    monkeypatch.setattr(akshare_cache, "_call_with_retry", lambda f, label: None)

    df = get_financial_report(symbol="600519", report_type="利润表")
    assert len(df) == 1


def test_dividend_yield_ttm_sums_recent_365_days(
    _yield_isolated_cache: None, monkeypatch: pytest.MonkeyPatch
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
    _yield_isolated_cache: None, monkeypatch: pytest.MonkeyPatch
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
    _yield_isolated_cache: None, monkeypatch: pytest.MonkeyPatch
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
    _yield_isolated_cache: None, monkeypatch: pytest.MonkeyPatch
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
    _yield_isolated_cache: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert get_dividend_yield("600000", 0.0) == 0.0


def test_dividend_yield_no_records_returns_zero(
    _yield_isolated_cache: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        akshare_cache.ak, "stock_history_dividend_detail",
        lambda symbol, indicator: pd.DataFrame(),
    )
    assert get_dividend_yield("600000", 10.0) == 0.0


def test_latest_dividend_detail_returns_most_recent(
    _yield_isolated_cache: None, monkeypatch: pytest.MonkeyPatch
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
    _yield_isolated_cache: None, monkeypatch: pytest.MonkeyPatch
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
    _yield_isolated_cache: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        akshare_cache.ak, "stock_history_dividend_detail",
        lambda symbol, indicator: pd.DataFrame(),
    )
    assert get_latest_dividend_detail("600000") is None


def test_compute_dividend_years_counts_consecutive():
    history = [
        ("2020", 0.3),
        ("2021", 0.4),
        ("2022", 0.5),
        ("2023", 0.6),
        ("2024", 0.7),
    ]
    assert _compute_dividend_years(history) == 5


def test_compute_dividend_years_empty():
    assert _compute_dividend_years([]) == 0


def test_get_dividend_history_fallback_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(symbol):
        raise RuntimeError("api error")

    monkeypatch.setattr(akshare_cache.ak, "stock_dividend_cninfo", boom)
    assert get_dividend_history("600036") == []


def test_get_dividend_history_returns_records(monkeypatch: pytest.MonkeyPatch) -> None:
    """正常返回分红记录."""
    df = pd.DataFrame({
        "年度": ["2020", "2021", "2022", "2023", "2024"],
        "分红金额": [0.3, 0.4, 0.5, 0.6, 0.7],
    })

    def fake_dividend(symbol):
        return df

    monkeypatch.setattr(akshare_cache.ak, "stock_dividend_cninfo", fake_dividend)
    result = get_dividend_history("600036", years=3)
    assert len(result) == 3
    assert result == [("2022", 0.5), ("2023", 0.6), ("2024", 0.7)]


def test_get_dividend_history_empty_df_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """API 返回空 DataFrame."""
    monkeypatch.setattr(
        akshare_cache.ak,
        "stock_dividend_cninfo",
        lambda symbol: pd.DataFrame(),
    )
    assert get_dividend_history("600036") == []


def test_get_dividend_history_none_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """API 返回 None."""
    monkeypatch.setattr(
        akshare_cache.ak,
        "stock_dividend_cninfo",
        lambda symbol: None,
    )
    assert get_dividend_history("600036") == []


def test_get_dividend_yield_sums_recent_12_months_dividends() -> None:
    """以最近除权除息日为锚,过去 365 天内的派息应被累加,÷10 得每股分红,÷股价得股息率。

    五粮液 000858(以 2026-07-16 为最近除权除息日,365 天窗口 [2025-07-16, 2026-07-16]):
      2026-07-16: 25.7969  (本财年年度分红,7 月)
      2025-12-18: 25.7800  (本财年中期分红,12 月)
      2025-07-18: 31.6900  (上财年年度分红,7 月,同月份应被排除)
    合计 51.5769 元/10股 = 5.15769 元/股
    股价 74.3 元,股息率 ≈ 6.94%
    """
    fake_df = _valuation_make_dividend_df()

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


def test_compute_pb_percentile_low_position():
    """当前 PB 在序列低端 -> 分位数低."""
    series = [("2024-01-01", 1.0), ("2024-02-01", 1.1), ("2024-03-01", 1.2),
              ("2024-04-01", 1.3), ("2024-05-01", 1.4)]
    # current 1.0 是最小值 -> 分位数 0.0
    pct = _compute_pb_percentile(series, current_pb=1.0)
    assert pct is not None
    assert pct < 0.1


def test_compute_pb_percentile_high_position():
    series = [("2024-01-01", 1.0), ("2024-02-01", 1.1), ("2024-03-01", 1.2),
              ("2024-04-01", 1.3), ("2024-05-01", 1.4)]
    pct = _compute_pb_percentile(series, current_pb=1.4)
    assert pct is not None
    assert pct > 0.9


def test_compute_pb_percentile_empty_series_returns_none():
    assert _compute_pb_percentile([], current_pb=1.0) is None


def test_compute_pb_percentile_single_point_returns_none():
    assert _compute_pb_percentile([("2024-01-01", 1.0)], current_pb=1.0) is None


def test_get_history_pb_fallback_to_empty_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(symbol, indicator, period):
        raise RuntimeError("api error")
    monkeypatch.setattr(akshare_cache.ak, "stock_zh_valuation_baidu", boom)
    result = get_history_pb("600036", years=5)
    assert result == []


def test_bank_special_returns_dict_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Level 1 成功返回银行专项指标."""
    fake_report = {
        "net_interest_margin": 0.015,
        "non_performing_loan_ratio": 0.012,
        "provision_coverage": 2.5,
        "core_tier1_capital_ratio": 0.095,
    }
    monkeypatch.setattr(
        akshare_cache,
        "_parse_bank_special_from_report",
        lambda symbol: fake_report,
    )
    result = get_bank_special_indicators("600036")
    assert result["net_interest_margin"] == 0.015
    assert result["non_performing_loan_ratio"] == 0.012
    assert result["provision_coverage"] == 2.5
    assert result["core_tier1_capital_ratio"] == 0.095


def test_bank_special_returns_empty_on_all_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    """全 fallback 失败返回空 dict."""
    monkeypatch.setattr(
        akshare_cache,
        "_parse_bank_special_from_report",
        lambda symbol: {},
    )
    monkeypatch.setattr(
        akshare_cache,
        "_online_search_metrics",
        lambda symbol, fields: {},
    )
    monkeypatch.setattr(
        akshare_cache,
        "_llm_estimate_metrics",
        lambda symbol, fields, hint: {},
    )
    result = get_bank_special_indicators("600036")
    assert result == {}


def test_bank_special_l1_exception_falls_through(monkeypatch: pytest.MonkeyPatch) -> None:
    """Level 1 抛异常时不死, 继续 fallback."""
    def boom(symbol):
        raise RuntimeError("parse error")

    monkeypatch.setattr(akshare_cache, "_parse_bank_special_from_report", boom)
    monkeypatch.setattr(
        akshare_cache,
        "_online_search_metrics",
        lambda symbol, fields: {"net_interest_margin": 0.016},
    )
    monkeypatch.setattr(
        akshare_cache,
        "_llm_estimate_metrics",
        lambda symbol, fields, hint: {},
    )
    result = get_bank_special_indicators("600036")
    assert result["net_interest_margin"] == 0.016


def test_bank_special_partial_missing_goes_to_l2(monkeypatch: pytest.MonkeyPatch) -> None:
    """L1 只返回部分指标, 剩余的走 L2/L3."""
    monkeypatch.setattr(
        akshare_cache,
        "_parse_bank_special_from_report",
        lambda symbol: {"net_interest_margin": 0.015},
    )
    monkeypatch.setattr(
        akshare_cache,
        "_online_search_metrics",
        lambda symbol, fields: {
            "non_performing_loan_ratio": 0.013,
            "provision_coverage": 2.6,
        },
    )
    monkeypatch.setattr(
        akshare_cache,
        "_llm_estimate_metrics",
        lambda symbol, fields, hint: {
            "core_tier1_capital_ratio": 0.098,
        },
    )
    result = get_bank_special_indicators("600036")
    assert result["net_interest_margin"] == 0.015
    assert result["non_performing_loan_ratio"] == 0.013
    assert result["provision_coverage"] == 2.6
    assert result["core_tier1_capital_ratio"] == 0.098


def test_r_and_d_expense_returns_dict_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """正常返回研发投入数据."""
    df = _make_income_df(rd=1.5e9, revenue=3e10, capitalized=3e8)
    monkeypatch.setattr(
        akshare_cache,
        "get_financial_report",
        lambda symbol, report_type, ttl_seconds=0, force_refresh=False: df,
    )
    result = get_r_and_d_expense("600276")
    assert "r_and_d_to_revenue" in result
    assert abs(result["r_and_d_to_revenue"] - 0.05) < 0.001
    assert "r_and_d_capitalization_rate" in result
    assert abs(result["r_and_d_capitalization_rate"] - 0.2) < 0.001


def test_r_and_d_expense_no_capitalized(monkeypatch: pytest.MonkeyPatch) -> None:
    """无资本化金额时只返回 r_and_d_to_revenue."""
    df = _make_income_df(rd=1e9, revenue=2e10)
    monkeypatch.setattr(
        akshare_cache,
        "get_financial_report",
        lambda symbol, report_type, ttl_seconds=0, force_refresh=False: df,
    )
    result = get_r_and_d_expense("000651")
    assert "r_and_d_to_revenue" in result
    assert "r_and_d_capitalization_rate" not in result


def test_r_and_d_expense_returns_empty_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """异常时返回空 dict."""
    def boom(symbol, report_type, ttl_seconds=0, force_refresh=False):
        raise RuntimeError("api error")

    monkeypatch.setattr(akshare_cache, "get_financial_report", boom)
    result = get_r_and_d_expense("600276")
    assert result == {}


def test_r_and_d_expense_returns_empty_on_empty_df(monkeypatch: pytest.MonkeyPatch) -> None:
    """返回空 DataFrame 时返回空 dict."""
    monkeypatch.setattr(
        akshare_cache,
        "get_financial_report",
        lambda symbol, report_type, ttl_seconds=0, force_refresh=False: pd.DataFrame(),
    )
    result = get_r_and_d_expense("600276")
    assert result == {}


def test_r_and_d_expense_returns_empty_on_none_df(monkeypatch: pytest.MonkeyPatch) -> None:
    """返回 None 时返回空 dict."""
    monkeypatch.setattr(
        akshare_cache,
        "get_financial_report",
        lambda symbol, report_type, ttl_seconds=0, force_refresh=False: None,
    )
    result = get_r_and_d_expense("600276")
    assert result == {}


def test_r_and_d_expense_handles_zero_revenue(monkeypatch: pytest.MonkeyPatch) -> None:
    """营收为 0 时跳过比率计算."""
    df = _make_income_df(rd=1e9, revenue=0)
    monkeypatch.setattr(
        akshare_cache,
        "get_financial_report",
        lambda symbol, report_type, ttl_seconds=0, force_refresh=False: df,
    )
    result = get_r_and_d_expense("600276")
    assert result == {}


def test_get_stock_name_cache_miss_then_hit(
    _stock_basic_isolated_cache: None, monkeypatch: pytest.MonkeyPatch
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
    _stock_basic_isolated_cache: None, monkeypatch: pytest.MonkeyPatch
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
    _stock_basic_isolated_cache: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """远程失败 -> 返回 None。"""
    def boom() -> pd.DataFrame:
        raise RuntimeError("network down")

    monkeypatch.setattr(stock_basic.ak, "stock_zh_a_spot_em", boom)
    assert stock_basic.get_stock_name("600519") is None


def test_get_stock_name_empty_symbol(_stock_basic_isolated_cache: None) -> None:
    """空 symbol -> 远程拉不到对应行 -> 返回 None（但不抛异常）。"""

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