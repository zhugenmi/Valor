"""Tests for akshare K-line fallback (_fetch_kline_via_akshare).

Verifies column mapping from akshare's Chinese schema to the same schema
produced by _prepare_history_frame, so fallback rows can be cached in the
same baostock_history_k table without downstream changes.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from valor.adapters.data.akshare_cache import _fetch_kline_via_akshare
from valor.adapters.data import akshare_cache as ac_module
from valor.adapters.data.baostock_client import BaoStockUnavailable
from valor.adapters.data.sqlite_cache import AkshareSQLiteCache


def _fake_akshare_df() -> pd.DataFrame:
    """Mimic ak.stock_zh_a_hist output schema."""
    return pd.DataFrame(
        {
            "日期": ["2026-07-15", "2026-07-16", "2026-07-17"],
            "开盘": [10.0, 10.5, 10.4],
            "收盘": [10.2, 10.4, 10.6],
            "最高": [10.5, 10.6, 10.8],
            "最低": [9.9, 10.3, 10.3],
            "成交量": [100000, 120000, 90000],
            "成交额": [1020000, 1248000, 954000],
            "振幅": [6.0, 2.9, 4.8],
            "涨跌幅": [2.0, 1.96, 1.92],
            "涨跌额": [0.2, 0.2, 0.2],
            "换手率": [1.0, 1.2, 0.9],
        }
    )


def test_fetch_kline_via_akshare_maps_columns_to_internal_schema():
    """akshare Chinese columns map to internal English schema."""
    with patch("valor.adapters.data.akshare_cache.ak.stock_zh_a_hist",
               return_value=_fake_akshare_df()):
        df = _fetch_kline_via_akshare(
            symbol="000858",
            start_date="2026-07-15",
            end_date="2026-07-17",
            adjust="qfq",
        )

    expected_columns = {
        "symbol", "adjust_flag", "date", "open", "high", "low", "close",
        "volume", "amount", "amplitude", "pct_change", "change_amount", "turnover",
    }
    assert set(df.columns) == expected_columns
    assert len(df) == 3
    assert df["symbol"].iloc[0] == "000858"
    assert df["adjust_flag"].iloc[0] == "qfq"
    # pct_change should be decimal (0.02), not percent (2.0)
    assert df["pct_change"].iloc[0] == pytest.approx(0.02)
    # turnover should be decimal (0.01), not percent (1.0)
    assert df["turnover"].iloc[0] == pytest.approx(0.01)
    # amplitude stays as percent (matches _prepare_history_frame)
    assert df["amplitude"].iloc[0] == pytest.approx(6.0)
    # volume: AkShare 成交量单位是"手",统一为"股"(* 100)与其他源对齐
    # 原始 100000 手 -> 10000000 股
    assert df["volume"].iloc[0] == pytest.approx(100000 * 100)
    # amount: AkShare 成交额单位已是"元",无需转换
    assert df["amount"].iloc[0] == pytest.approx(1020000)
    # date column is datetime
    assert pd.api.types.is_datetime64_any_dtype(df["date"])


def test_fetch_kline_via_akshare_returns_empty_when_akshare_fails():
    """When ak.stock_zh_a_hist returns None/empty, fallback returns empty df."""
    with patch("valor.adapters.data.akshare_cache.ak.stock_zh_a_hist",
               return_value=pd.DataFrame()):
        df = _fetch_kline_via_akshare(
            symbol="000858",
            start_date="2026-07-15",
            end_date="2026-07-17",
            adjust="qfq",
        )
    assert df.empty


def test_fetch_kline_via_akshare_returns_empty_on_exception():
    """When ak.stock_zh_a_hist raises, _call_with_retry returns None -> empty df."""
    with patch("valor.adapters.data.akshare_cache.ak.stock_zh_a_hist",
               side_effect=RuntimeError("akshare down")):
        df = _fetch_kline_via_akshare(
            symbol="000858",
            start_date="2026-07-15",
            end_date="2026-07-17",
            adjust="qfq",
        )
    assert df.empty


def test_fetch_kline_via_akshare_handles_missing_columns_gracefully():
    """If akshare returns a subset of columns, missing fields default to 0."""
    partial = pd.DataFrame(
        {
            "日期": ["2026-07-15"],
            "开盘": [10.0],
            "收盘": [10.2],
            "最高": [10.5],
            "最低": [9.9],
            "成交量": [100000],
        }
    )
    with patch("valor.adapters.data.akshare_cache.ak.stock_zh_a_hist",
               return_value=partial):
        df = _fetch_kline_via_akshare(
            symbol="000858",
            start_date="2026-07-15",
            end_date="2026-07-15",
            adjust="qfq",
        )
    assert len(df) == 1
    assert df["close"].iloc[0] == pytest.approx(10.2)
    # amount/turnover/amplitude absent -> default 0
    assert df["amount"].iloc[0] == 0
    assert df["turnover"].iloc[0] == 0


# ---------------------------------------------------------------------------
# Task 3: Fallback wiring in get_price_history_df
# ---------------------------------------------------------------------------


def _fake_akshare_df_for_range(trading_days: list[str]) -> pd.DataFrame:
    """Build a fake akshare df covering the given trading days."""
    n = len(trading_days)
    return pd.DataFrame({
        "日期": trading_days,
        "开盘": [10.0] * n,
        "收盘": [10.2] * n,
        "最高": [10.5] * n,
        "最低": [9.9] * n,
        "成交量": [100000] * n,
        "成交额": [1020000] * n,
        "振幅": [6.0] * n,
        "涨跌幅": [2.0] * n,
        "涨跌额": [0.2] * n,
        "换手率": [1.0] * n,
    })


@pytest.fixture
def temp_cache(monkeypatch: pytest.MonkeyPatch, tmp_path) -> AkshareSQLiteCache:
    cache = AkshareSQLiteCache(tmp_path / "test.db")
    monkeypatch.setattr(ac_module, "cache", cache)
    return cache


def _trade_dates_df(start: str, end: str) -> pd.DataFrame:
    dates = pd.bdate_range(start=start, end=end)
    return pd.DataFrame({
        "calendar_date": dates.strftime("%Y-%m-%d"),
        "is_trading_day": [1] * len(dates),
    })


def test_get_price_history_df_falls_back_to_akshare_on_baostock_blacklist(temp_cache):
    """When BaoStock raises BaoStockUnavailable, akshare fallback fills the gap."""
    start_dt = pd.Timestamp("2026-07-13")
    end_dt = pd.Timestamp("2026-07-17")

    trading_days = list(pd.bdate_range("2026-07-13", "2026-07-17").strftime("%Y-%m-%d"))

    def baostock_unavailable(*args, **kwargs):
        raise BaoStockUnavailable("circuit open")

    with patch("valor.adapters.data.akshare_cache.query_trade_dates",
               return_value=_trade_dates_df("2026-07-13", "2026-07-17")), \
         patch("valor.adapters.data.akshare_cache.query_history_k_data_plus",
               side_effect=baostock_unavailable), \
         patch("valor.adapters.data.akshare_cache.ak.stock_zh_a_hist",
               return_value=_fake_akshare_df_for_range(trading_days)):
        df = ac_module.get_price_history_df(
            symbol="000858",
            start_date=start_dt,
            end_date=end_dt,
            adjust="qfq",
        )

    assert not df.empty
    # Should have rows for the trading days in range
    assert len(df) >= 1
    # Verify data was cached (akshare rows went into baostock_history_k)
    cached = temp_cache.fetch_records(
        table=ac_module.HISTORY_TABLE,
        filters={"symbol": "000858", "adjust_flag": "qfq"},
    )
    assert len(cached) >= 1


def test_get_price_history_df_returns_cached_when_both_sources_fail(temp_cache):
    """If both BaoStock and akshare fail, cached segments are still returned."""
    start_dt = pd.Timestamp("2026-07-13")
    end_dt = pd.Timestamp("2026-07-17")

    # Pre-seed cache with one row in range
    seed_df = pd.DataFrame([{
        "symbol": "000858",
        "adjust_flag": "qfq",
        "date": pd.Timestamp("2026-07-13"),
        "open": 10.0, "high": 10.5, "low": 9.9, "close": 10.2,
        "volume": 100000, "amount": 1020000,
        "amplitude": 6.0, "pct_change": 0.02,
        "change_amount": 0.2, "turnover": 0.01,
    }])
    temp_cache.upsert_records(
        table=ac_module.HISTORY_TABLE,
        records=seed_df.to_dict("records"),
        key_columns=["symbol", "adjust_flag", "date"],
    )

    with patch("valor.adapters.data.akshare_cache.query_trade_dates",
               return_value=_trade_dates_df("2026-07-13", "2026-07-17")), \
         patch("valor.adapters.data.akshare_cache.query_history_k_data_plus",
               side_effect=BaoStockUnavailable("circuit open")), \
         patch("valor.adapters.data.akshare_cache.ak.stock_zh_a_hist",
               return_value=pd.DataFrame()):
        df = ac_module.get_price_history_df(
            symbol="000858",
            start_date=start_dt,
            end_date=end_dt,
            adjust="qfq",
        )

    # Should still return the cached row, not empty
    assert not df.empty
    assert pd.Timestamp("2026-07-13") in df["date"].dt.normalize().tolist()


def test_get_price_history_df_falls_back_when_query_trade_dates_fails(temp_cache):
    """When query_trade_dates raises BaoStockUnavailable (BaoStock blacklisted),
    get_price_history_df must still return data via the akshare K-line fallback.

    This reproduces the production blacklist scenario: ensure_login() fails inside
    query_trade_dates BEFORE the missing-segment loop's try/except can catch it.
    The fix wraps _expected_trading_days so it falls back to bdate_range.
    """
    start_dt = pd.Timestamp("2026-07-13")
    end_dt = pd.Timestamp("2026-07-17")

    trading_days = list(pd.bdate_range("2026-07-13", "2026-07-17").strftime("%Y-%m-%d"))

    # query_trade_dates raises (simulating BaoStock blacklist);
    # query_history_k_data_plus also raises (same blacklist);
    # akshare must fill the gap.
    with patch("valor.adapters.data.akshare_cache.query_trade_dates",
               side_effect=BaoStockUnavailable("circuit open")), \
         patch("valor.adapters.data.akshare_cache.query_history_k_data_plus",
               side_effect=BaoStockUnavailable("circuit open")), \
         patch("valor.adapters.data.akshare_cache.ak.stock_zh_a_hist",
               return_value=_fake_akshare_df_for_range(trading_days)):
        df = ac_module.get_price_history_df(
            symbol="000858",
            start_date=start_dt,
            end_date=end_dt,
            adjust="qfq",
        )

    assert not df.empty
    # akshare rows should be cached
    cached = temp_cache.fetch_records(
        table=ac_module.HISTORY_TABLE,
        filters={"symbol": "000858", "adjust_flag": "qfq"},
    )
    assert len(cached) >= 1


# ---------------------------------------------------------------------------
# Bug B: _expected_trading_days fallback chain
# (BaoStock query_trade_dates -> akshare tool_trade_date_hist_sina -> bdate_range)
# ---------------------------------------------------------------------------


def _fake_sina_trade_calendar(extra_dates: list[str] | None = None) -> pd.DataFrame:
    """Mimic ak.tool_trade_date_hist_sina output: a single trade_date column.

    Includes real trading days for 2026-06 (端午 6/19-6/21 excluded) to verify
    the fallback correctly excludes holidays.
    """
    dates = [
        "2026-06-15", "2026-06-16", "2026-06-17", "2026-06-18",
        # 2026-06-19/20/21 端午节 - should be absent
        "2026-06-22", "2026-06-23", "2026-06-24", "2026-06-25",
    ]
    if extra_dates:
        dates.extend(extra_dates)
    return pd.DataFrame({"trade_date": sorted(dates)})


def test_expected_trading_days_falls_back_to_akshare_calendar():
    """When BaoStock query_trade_dates fails, akshare tool_trade_date_hist_sina
    provides the real trading calendar (holidays excluded)."""
    from datetime import datetime

    start = datetime(2026, 6, 15)
    end = datetime(2026, 6, 25)

    with patch("valor.adapters.data.akshare_cache.query_trade_dates",
               side_effect=BaoStockUnavailable("circuit open")), \
         patch("valor.adapters.data.akshare_cache.ak.tool_trade_date_hist_sina",
               return_value=_fake_sina_trade_calendar()):
        days = ac_module._expected_trading_days(start, end)

    # 端午 6/19-6/21 must NOT appear in the result
    day_strs = [d.strftime("%Y-%m-%d") for d in days]
    for holiday in ("2026-06-19", "2026-06-20", "2026-06-21"):
        assert holiday not in day_strs, f"{holiday} should be excluded as 端午 holiday"
    # Real trading days must be present
    for trading_day in ("2026-06-15", "2026-06-18", "2026-06-22", "2026-06-25"):
        assert trading_day in day_strs


def test_expected_trading_days_final_fallback_bdate_range():
    """When both BaoStock and akshare trade calendar fail, fall back to bdate_range
    (last resort, includes holidays but at least returns something)."""
    from datetime import datetime

    start = datetime(2026, 6, 15)
    end = datetime(2026, 6, 25)

    with patch("valor.adapters.data.akshare_cache.query_trade_dates",
               side_effect=BaoStockUnavailable("circuit open")), \
         patch("valor.adapters.data.akshare_cache.ak.tool_trade_date_hist_sina",
               side_effect=RuntimeError("akshare down too")):
        days = ac_module._expected_trading_days(start, end)

    # bdate_range returns Mon-Fri, so 6/19 (Fri) should be present
    # (this is the known limitation - bdate_range doesn't know about holidays)
    day_strs = [d.strftime("%Y-%m-%d") for d in days]
    assert "2026-06-19" in day_strs  # bdate_range includes it (limitation)
    assert len(days) > 0


def test_get_price_history_df_no_holiday_double_source_warnings(
    temp_cache, caplog: pytest.LogCaptureFixture
):
    """When BaoStock is blacklisted and akshare trade calendar is used as fallback,
    holiday segments (e.g. 端午 6/19-6/21) must NOT appear in missing_segments
    and therefore NOT trigger spurious "K线双源均失败" warnings.

    Bug B regression: pd.bdate_range fallback treated holidays as missing
    trading days, causing akshare to be called for holiday segments (which
    return empty) and logging false "double-source failure" warnings.
    """
    from datetime import datetime

    start_dt = datetime(2026, 6, 15)
    end_dt = datetime(2026, 6, 25)

    # Real trading days for 2026-06-15..25, excluding 端午 6/19-6/21
    trading_days = [
        "2026-06-15", "2026-06-16", "2026-06-17", "2026-06-18",
        "2026-06-22", "2026-06-23", "2026-06-24", "2026-06-25",
    ]

    with patch("valor.adapters.data.akshare_cache.query_trade_dates",
               side_effect=BaoStockUnavailable("circuit open")), \
         patch("valor.adapters.data.akshare_cache.query_history_k_data_plus",
               side_effect=BaoStockUnavailable("circuit open")), \
         patch("valor.adapters.data.akshare_cache.ak.tool_trade_date_hist_sina",
               return_value=_fake_sina_trade_calendar()), \
         patch("valor.adapters.data.akshare_cache.ak.stock_zh_a_hist",
               return_value=_fake_akshare_df_for_range(trading_days)):
        df = ac_module.get_price_history_df(
            symbol="000858",
            start_date=start_dt,
            end_date=end_dt,
            adjust="qfq",
        )

    assert not df.empty
    # No "双源均失败" warning should appear (no holiday segments were attempted)
    assert "双源均失败" not in caplog.text, (
        f"holiday segments should not be attempted; got warnings: {caplog.text}"
    )
    # Specifically, 端午 6/19 must not appear in any warning
    assert "2026-06-19" not in caplog.text


# ---------------------------------------------------------------------------
# Tushare third-tier fallback (BaoStock -> AkShare -> Tushare)
# ---------------------------------------------------------------------------


def _fake_tushare_daily_df(trading_days: list[str]) -> pd.DataFrame:
    """Mimic Tushare pro.daily() output. vol in 手, amount in 千元."""
    n = len(trading_days)
    return pd.DataFrame({
        "ts_code": ["600519.SH"] * n,
        "trade_date": [d.replace("-", "") for d in trading_days],
        "open": [10.0] * n,
        "high": [10.5] * n,
        "low": [9.9] * n,
        "close": [10.2] * n,
        "pre_close": [10.0] * n,
        "change": [0.2] * n,
        "pct_chg": [2.0] * n,
        "vol": [1000.0] * n,        # 手
        "amount": [1020.0] * n,      # 千元
    })


def test_fetch_kline_via_tushare_maps_columns_and_units(temp_cache):
    """Tushare daily fields map to unified schema with correct unit conversion."""
    from valor.adapters.data.akshare_cache import _fetch_kline_via_tushare

    fake_df = _fake_tushare_daily_df(["2026-07-15", "2026-07-16"])

    mock_client = MagicMock()
    mock_client.available = True
    mock_client.query_daily = MagicMock(return_value=fake_df)

    with patch("valor.adapters.data.akshare_cache._get_tushare_client",
               return_value=mock_client):
        df = _fetch_kline_via_tushare(
            symbol="600519",
            start_date="2026-07-15",
            end_date="2026-07-16",
            adjust="qfq",
        )

    expected_columns = {
        "symbol", "adjust_flag", "date", "open", "high", "low", "close",
        "volume", "amount", "amplitude", "pct_change", "change_amount", "turnover",
    }
    assert set(df.columns) == expected_columns
    assert len(df) == 2
    # Tushare adjust is unadjusted -> adjust_flag = ""
    assert (df["adjust_flag"] == "").all()
    # vol 1000 手 -> 100000 股
    assert df["volume"].iloc[0] == pytest.approx(1000.0 * 100)
    # amount 1020 千元 -> 1020000 元
    assert df["amount"].iloc[0] == pytest.approx(1020.0 * 1000)
    # pct_chg 2.0 (%) -> 0.02 (decimal)
    assert df["pct_change"].iloc[0] == pytest.approx(0.02)
    # amplitude computed: (10.5 - 9.9) / 10.0 * 100 = 6.0
    assert df["amplitude"].iloc[0] == pytest.approx(6.0)
    # Tushare daily has no turnover -> 0.0
    assert (df["turnover"] == 0.0).all()
    # date is datetime
    assert pd.api.types.is_datetime64_any_dtype(df["date"])


def test_fetch_kline_via_tushare_no_token_returns_empty(temp_cache, monkeypatch):
    """Without TUSHARE_TOKEN, _fetch_kline_via_tushare returns empty df."""
    from valor.adapters.data.akshare_cache import _fetch_kline_via_tushare

    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    df = _fetch_kline_via_tushare(
        symbol="600519",
        start_date="2026-07-15",
        end_date="2026-07-16",
        adjust="qfq",
    )
    assert df.empty


def test_get_price_history_df_falls_back_to_tushare_when_baostock_and_akshare_fail(
    temp_cache, monkeypatch
):
    """Three-tier fallback: BaoStock fails -> AkShare fails -> Tushare succeeds."""
    monkeypatch.setenv("TUSHARE_TOKEN", "fake-token")

    start_dt = pd.Timestamp("2026-07-13")
    end_dt = pd.Timestamp("2026-07-17")
    trading_days = list(pd.bdate_range("2026-07-13", "2026-07-17").strftime("%Y-%m-%d"))

    mock_tushare_client = MagicMock()
    mock_tushare_client.available = True
    mock_tushare_client.query_daily = MagicMock(
        return_value=_fake_tushare_daily_df(trading_days)
    )

    with patch("valor.adapters.data.akshare_cache.query_trade_dates",
               return_value=_trade_dates_df("2026-07-13", "2026-07-17")), \
         patch("valor.adapters.data.akshare_cache.query_history_k_data_plus",
               side_effect=BaoStockUnavailable("circuit open")), \
         patch("valor.adapters.data.akshare_cache.ak.stock_zh_a_hist",
               return_value=pd.DataFrame()), \
         patch("valor.adapters.data.akshare_cache._get_tushare_client",
               return_value=mock_tushare_client):
        df = ac_module.get_price_history_df(
            symbol="600519",
            start_date=start_dt,
            end_date=end_dt,
            adjust="qfq",
        )

    assert not df.empty
    assert len(df) >= 1
    # Tushare rows cached in the same baostock_history_k table
    cached = temp_cache.fetch_records(
        table=ac_module.HISTORY_TABLE,
        filters={"symbol": "600519"},
    )
    assert len(cached) >= 1
    # Verify unit conversion persisted to cache (vol 1000 手 -> 100000 股)
    assert cached[0]["volume"] == pytest.approx(1000.0 * 100)
