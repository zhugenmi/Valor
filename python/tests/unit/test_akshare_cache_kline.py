"""Tests for akshare K-line fallback (_fetch_kline_via_akshare).

Verifies column mapping from akshare's Chinese schema to the same schema
produced by _prepare_history_frame, so fallback rows can be cached in the
same baostock_history_k table without downstream changes.
"""

from __future__ import annotations

from unittest.mock import patch

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
