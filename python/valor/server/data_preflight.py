"""Pre-flight check: ensure latest trading day's K-line data exists in cache.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict

from valor.adapters.data.akshare_cache import (
    HISTORY_TABLE,
    cache,
    get_latest_trading_day,
    get_price_history_df,
)


def ensure_latest_trading_day_data(ticker: str) -> Dict[str, object]:
    """Check if latest trading day's K-line for `ticker` is cached; fetch if missing.

    Returns:
        {"trading_day": "YYYY-MM-DD", "filled": bool}
        - filled=True: data was missing, we attempted to fetch
        - filled=False: cache already had the latest trading day
    """
    latest = get_latest_trading_day()
    latest_str = latest.strftime("%Y-%m-%d")

    cached = cache.fetch_records(
        table=HISTORY_TABLE,
        filters={"symbol": ticker, "date": latest_str},
        limit=1,
    )
    if cached:
        return {"trading_day": latest_str, "filled": False}

    # Trigger incremental fetch over a 10-day window ending at latest
    start = latest - timedelta(days=10)
    try:
        get_price_history_df(
            symbol=ticker,
            start_date=datetime.combine(start, datetime.min.time()),
            end_date=datetime.combine(latest, datetime.min.time()),
        )
    except Exception:
        # Best-effort; workflow will run with whatever cache exists
        pass
    return {"trading_day": latest_str, "filled": True}


__all__ = ["ensure_latest_trading_day_data"]
