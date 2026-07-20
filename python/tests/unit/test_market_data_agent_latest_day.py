"""Test market_data_agent uses latest trading day for end_date. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

from valor.agents.market_data import market_data_agent


def _build_state(end_date=None):
    return {
        "messages": [],
        "data": {
            "ticker": "600519",
            "start_date": None,
            "end_date": end_date,
        },
        "metadata": {"show_reasoning": False},
    }


def test_default_end_date_uses_latest_trading_day():
    """If data.end_date is None, agent should resolve to get_latest_trading_day(),
    not just yesterday. On 2026-07-20 (Mon) -> 2026-07-17 (Fri)."""
    with (
        patch("valor.agents.market_data.get_price_history", return_value=None),
        patch("valor.agents.market_data.get_market_data", return_value={"market_cap": 0}),
        patch("valor.agents.market_data.get_financial_metrics", return_value=[]),
        patch("valor.agents.market_data.get_financial_statements", return_value=[]),
        patch("valor.agents.market_data.get_market_snapshot", return_value=None),
        patch(
            "valor.agents.market_data.get_latest_trading_day",
            return_value=date(2026, 7, 17),
        ),
        patch("valor.agents.market_data.datetime") as mock_dt,
    ):
        from datetime import datetime as real_dt

        mock_dt.now.return_value = real_dt(2026, 7, 20, 10, 0, 0)
        mock_dt.side_effect = real_dt
        mock_dt.strptime = real_dt.strptime

        result = market_data_agent(_build_state(end_date=None))

    # Before fix: end_date = yesterday = "2026-07-19" (Sunday) -> FAIL
    # After fix: end_date = latest trading day = "2026-07-17" (Friday) -> PASS
    assert result["data"]["end_date"] == "2026-07-17"