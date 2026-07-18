"""Tests for get_price_history_df log message accuracy.

Verifies that the "missing days" count in the cache-miss log message
reports actual trading days (not calendar days) when the date range
spans weekends/holidays.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from valor.adapters.data import akshare_cache
from valor.adapters.data.sqlite_cache import AkshareSQLiteCache


@pytest.fixture
def temp_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AkshareSQLiteCache:
    """Replace module-level cache with a temp SQLite cache."""
    cache = AkshareSQLiteCache(tmp_path / "test.db")
    monkeypatch.setattr(akshare_cache, "cache", cache)
    return cache


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
