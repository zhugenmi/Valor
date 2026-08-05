"""Unit tests for AkshareSQLiteCache.

Covers upsert/fetch round-trip, TTL expiration, dedup on key conflict,
column filtering, and record deletion.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from valor.adapters.data import akshare_cache
from valor.adapters.data.akshare_cache import get_latest_trading_day
from valor.adapters.data.sqlite_cache import AkshareSQLiteCache


@pytest.fixture
def cache(tmp_path: Path) -> AkshareSQLiteCache:
    """Return a cache backed by a temp SQLite file."""
    return AkshareSQLiteCache(database_path=tmp_path / "test.db")


@pytest.fixture
def temp_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AkshareSQLiteCache:
    """Replace module-level cache with a temp SQLite cache."""
    cache = AkshareSQLiteCache(tmp_path / "test.db")
    monkeypatch.setattr(akshare_cache, "cache", cache)
    return cache


def _mock_trade_dates(start: date, end: date) -> pd.DataFrame:
    """Return a fake trade calendar where 2026-07-17 (Fri) is the last trading day
    on or before 2026-07-20 (Mon). 2026-07-18/19 are weekend."""
    rows = []
    d = pd.Timestamp(start)
    while d <= pd.Timestamp(end):
        is_trading = d.weekday() < 5  # Mon-Fri
        rows.append({"calendar_date": d.strftime("%Y-%m-%d"), "is_trading_day": int(is_trading)})
        d += pd.Timedelta(days=1)
    return pd.DataFrame(rows)


def _make_trade_dates_df(start: str, end: str) -> pd.DataFrame:
    """Build a trade-dates dataframe where weekdays are trading days."""
    dates = pd.bdate_range(start=start, end=end)
    return pd.DataFrame(
        {
            "calendar_date": dates.strftime("%Y-%m-%d"),
            "is_trading_day": [1] * len(dates),
        }
    )


def _make_kline_df(symbol: str, dates: list[str]) -> pd.DataFrame:
    """Build a minimal BaoStock-style kline dataframe."""
    n = len(dates)
    return pd.DataFrame(
        {
            "date": dates,
            "open": [6.0] * n,
            "high": [6.5] * n,
            "low": [5.8] * n,
            "close": [6.2] * n,
            "preclose": [6.0] * n,
            "volume": [1000000] * n,
            "amount": [6200000] * n,
            "pctChg": [1.0] * n,
            "turn": [1.0] * n,
        }
    )


def test_upsert_and_fetch_round_trip(cache: AkshareSQLiteCache) -> None:
    """After upsert, fetch_records returns the stored record."""
    cache.upsert_records(
        table="realtime",
        records=[{"代码": "600519", "close": 10.0}],
        key_columns=["代码"],
    )
    result = cache.fetch_records(table="realtime")
    assert len(result) == 1
    assert result[0]["代码"] == "600519"
    assert result[0]["close"] == 10.0


def test_fetch_unknown_table_returns_empty(cache: AkshareSQLiteCache) -> None:
    """Fetching a table that does not exist returns an empty list."""
    result = cache.fetch_records(table="nonexistent")
    assert result == []


def test_ttl_expiration(cache: AkshareSQLiteCache) -> None:
    """Records are filtered out when ttl_seconds=0 (threshold is now)."""
    cache.upsert_records(
        table="realtime",
        records=[{"代码": "600519", "close": 10.0}],
        key_columns=["代码"],
    )
    result = cache.fetch_records(table="realtime", ttl_seconds=0)
    assert result == []


def test_upsert_dedup_on_key_conflict(cache: AkshareSQLiteCache) -> None:
    """Upserting with the same key replaces the row instead of inserting a duplicate."""
    cache.upsert_records(
        table="realtime",
        records=[{"代码": "600519", "close": 10.0}],
        key_columns=["代码"],
    )
    cache.upsert_records(
        table="realtime",
        records=[{"代码": "600519", "close": 20.0}],
        key_columns=["代码"],
    )
    result = cache.fetch_records(table="realtime")
    assert len(result) == 1
    assert result[0]["close"] == 20.0


def test_fetch_with_column_filter(cache: AkshareSQLiteCache) -> None:
    """fetch_records with a filter dict returns only matching rows."""
    cache.upsert_records(
        table="realtime",
        records=[
            {"代码": "600519", "close": 10.0},
            {"代码": "000001", "close": 5.0},
        ],
        key_columns=["代码"],
    )
    result = cache.fetch_records(table="realtime", filters={"代码": "600519"})
    assert len(result) == 1
    assert result[0]["代码"] == "600519"
    assert result[0]["close"] == 10.0


def test_delete_records(cache: AkshareSQLiteCache) -> None:
    """delete_records with a filter removes matching rows."""
    cache.upsert_records(
        table="realtime",
        records=[
            {"代码": "600519", "close": 10.0},
            {"代码": "000001", "close": 5.0},
        ],
        key_columns=["代码"],
    )
    cache.delete_records(table="realtime", filters={"代码": "600519"})
    result = cache.fetch_records(table="realtime")
    assert len(result) == 1
    assert result[0]["代码"] == "000001"


def test_saturday_returns_friday():
    """周六 (2026-07-18) 诊断应返回周五 (2026-07-17)."""
    with patch(
        "valor.adapters.data.akshare_cache.query_trade_dates",
        side_effect=_mock_trade_dates,
    ):
        result = get_latest_trading_day(date(2026, 7, 18))
    assert result == date(2026, 7, 17)


def test_sunday_returns_friday():
    with patch(
        "valor.adapters.data.akshare_cache.query_trade_dates",
        side_effect=_mock_trade_dates,
    ):
        result = get_latest_trading_day(date(2026, 7, 19))
    assert result == date(2026, 7, 17)


def test_monday_returns_monday_if_trading():
    """周一 (2026-07-20) 是交易日，应返回自身."""
    with patch(
        "valor.adapters.data.akshare_cache.query_trade_dates",
        side_effect=_mock_trade_dates,
    ):
        result = get_latest_trading_day(date(2026, 7, 20))
    assert result == date(2026, 7, 20)


def test_none_defaults_to_today():
    """today=None 应使用 date.today()，不抛异常."""
    with patch(
        "valor.adapters.data.akshare_cache.query_trade_dates",
        side_effect=_mock_trade_dates,
    ):
        result = get_latest_trading_day()
    assert isinstance(result, date)


def test_price_history_log_reports_trading_days_not_calendar_days(
    temp_cache: AkshareSQLiteCache,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Cache-miss log counts trading days (excludes weekends), not calendar days.

    Date range 2026-07-07 (Tue) to 2026-07-17 (Fri) spans 11 calendar days
    but only 9 trading days (weekends excluded). The log must say 9.
    """
    start_dt = datetime(2026, 7, 7)
    end_dt = datetime(2026, 7, 17)

    trade_dates = _make_trade_dates_df("2026-07-07", "2026-07-17")
    # Trading days: 07-07, 07-08, 07-09, 07-10, 07-13, 07-14, 07-15, 07-16, 07-17 = 9

    trading_days = list(pd.bdate_range("2026-07-07", "2026-07-17").strftime("%Y-%m-%d"))

    def fake_query_history(symbol: str, start_date: str, end_date: str, adjust: str) -> pd.DataFrame:
        return _make_kline_df(symbol, trading_days)

    with patch(
        "valor.adapters.data.akshare_cache.query_trade_dates",
        return_value=trade_dates,
    ), patch(
        "valor.adapters.data.akshare_cache.query_history_k_data_plus",
        side_effect=fake_query_history,
    ):
        with caplog.at_level(logging.INFO, logger="akshare_cache"):
            akshare_cache.get_price_history_df(
                symbol="000725",
                start_date=start_dt,
                end_date=end_dt,
                adjust="qfq",
            )

    # Find the cache-miss log line
    miss_logs = [r.message for r in caplog.records if "缺少" in r.message]
    assert miss_logs, "Expected a cache-miss log message"
    log_msg = miss_logs[0]

    # Should report 9 trading days, not 11 calendar days
    assert "9 个交易日" in log_msg
    assert "11 个交易日" not in log_msg