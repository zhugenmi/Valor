"""Tests for get_latest_trading_day. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pandas as pd

from valor.adapters.data.akshare_cache import get_latest_trading_day


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