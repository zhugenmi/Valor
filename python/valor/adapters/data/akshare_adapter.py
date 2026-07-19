"""AkShare async adapter wrapping A_Share's free-function cache module.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

import asyncio
from datetime import datetime

import pandas as pd
from loguru import logger

from valor.adapters.data.akshare_cache import (
    get_financial_indicators,
    get_price_history_df,
    get_stock_news,
    get_stock_spot_row,
)


class AkShareAdapter:
    """Async wrapper around A_Share's cached AkShare free functions."""

    async def get_realtime_quote(self, ticker: str) -> pd.DataFrame:
        """Return realtime quote row for a single ticker."""
        row = await asyncio.to_thread(get_stock_spot_row, ticker)
        if row is None:
            logger.warning("AkShare realtime miss for {ticker}", ticker=ticker)
            return pd.DataFrame()
        return row.to_frame().T

    async def get_daily_history(
        self, ticker: str, start: str, end: str
    ) -> pd.DataFrame:
        """Return daily OHLCV history between start and end (YYYY-MM-DD)."""
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d")
        return await asyncio.to_thread(
            get_price_history_df,
            symbol=ticker,
            start_date=start_dt,
            end_date=end_dt,
            adjust="qfq",
        )

    async def get_financial_indicators(self, ticker: str) -> pd.DataFrame:
        """Return financial analysis indicators (新浪接口).

        start_year 由 akshare_cache 自动推算（首刷近 5 年，增量用 MAX(日期).year）。
        """
        return await asyncio.to_thread(
            get_financial_indicators,
            symbol=ticker,
        )

    async def get_news(self, ticker: str, limit: int = 20) -> pd.DataFrame:
        """Return recent news for ticker (limited by limit)."""
        df = await asyncio.to_thread(get_stock_news, symbol=ticker)
        return df.head(limit)
