"""Tests for data_preflight. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pandas as pd

from valor.server.data_preflight import ensure_latest_trading_day_data


def test_returns_filled_false_when_cache_has_latest_day():
    """Cache already contains 2026-07-17 -> filled=False, no fetch."""
    with (
        patch(
            "valor.server.data_preflight.get_latest_trading_day",
            return_value=date(2026, 7, 17),
        ),
        patch("valor.server.data_preflight.cache") as mock_cache,
    ):
        mock_cache.fetch_records.return_value = [{"date": "2026-07-17"}]
        result = ensure_latest_trading_day_data("600519")
    assert result == {"trading_day": "2026-07-17", "filled": False}


def test_returns_filled_true_when_cache_missing():
    """Cache doesn't have 2026-07-17 -> trigger get_price_history_df, filled=True."""
    with (
        patch(
            "valor.server.data_preflight.get_latest_trading_day",
            return_value=date(2026, 7, 17),
        ),
        patch("valor.server.data_preflight.cache") as mock_cache,
        patch("valor.server.data_preflight.get_price_history_df") as mock_fetch,
    ):
        mock_cache.fetch_records.return_value = []
        mock_fetch.return_value = pd.DataFrame({"date": [pd.Timestamp("2026-07-17")]})
        result = ensure_latest_trading_day_data("600519")
    assert result == {"trading_day": "2026-07-17", "filled": True}
    # Verify fetch was called with end_date matching the latest trading day
    _, kwargs = mock_fetch.call_args
    end_date = kwargs.get("end_date")
    assert end_date is not None
    # end_date is a datetime; its .date() should equal 2026-07-17
    assert end_date.date() == date(2026, 7, 17)


def test_returns_filled_true_even_if_fetch_returns_empty():
    """If fetch returns empty (source unavailable), still report filled=True so
    the UI knows we attempted. Workflow may then run with stale cache."""
    with (
        patch(
            "valor.server.data_preflight.get_latest_trading_day",
            return_value=date(2026, 7, 17),
        ),
        patch("valor.server.data_preflight.cache") as mock_cache,
        patch("valor.server.data_preflight.get_price_history_df", return_value=pd.DataFrame()),
    ):
        mock_cache.fetch_records.return_value = []
        result = ensure_latest_trading_day_data("600519")
    assert result == {"trading_day": "2026-07-17", "filled": True}
