"""DataRouter-backed lookup adapters for portfolio analytics.

Implements PriceLookup, HistoricalLookup, and SectorLookup protocols
using valor's DataRouter as the underlying data source.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
from __future__ import annotations

import time
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from valor.adapters.data.router import DataRouter

from valor.adapters.data.akshare_cache import is_market_open


class DataRouterPriceLookup:
    """PriceLookup protocol implementation backed by DataRouter.

    Tries realtime quote first, falls back to daily history close.
    A short class-level TTL cache bridges adjacent requests (e.g.
    ``list_portfolios`` followed by ``get_analytics``) so the same ticker
    is not re-fetched over the network within ~60s.
    """

    _CACHE_TTL = 60.0  # seconds
    # Class-level so all instances in the same process share the cache.
    _cache: dict[tuple[str, date], tuple[float, Decimal]] = {}

    def __init__(self, router: DataRouter) -> None:
        self._router = router

    async def get(self, ticker: str, as_of: date) -> Decimal:
        key = (ticker, as_of)
        now = time.monotonic()
        cached = DataRouterPriceLookup._cache.get(key)
        if cached is not None:
            ts, price = cached
            if now - ts < DataRouterPriceLookup._CACHE_TTL:
                return price

        # During trading hours try realtime quote first; outside trading hours
        # skip it entirely - the spot endpoint returns a stale intraday price
        # that disagrees with the daily close, and the network call usually
        # fails anyway. Fall straight through to daily history (yesterday's close).
        if is_market_open():
            try:
                df = await self._router.get_realtime_quote(ticker)
                if df is not None and not df.empty:
                    row = df.iloc[0]
                    raw = row.get("最新价", row.get("price", None))
                    if raw is not None:
                        price = Decimal(str(raw))
                        DataRouterPriceLookup._cache[key] = (now, price)
                        return price
            except Exception:
                pass

        # Fallback: last close from recent daily history
        end = as_of.isoformat()
        start = (as_of - timedelta(days=30)).isoformat()
        hist = await self._router.get_daily_history(ticker, start, end)
        if hist is not None and not hist.empty:
            raw = hist.iloc[-1].get("close", hist.iloc[-1].get("收盘", None))
            if raw is not None:
                price = Decimal(str(raw))
                DataRouterPriceLookup._cache[key] = (now, price)
                return price

        raise ValueError(f"no price available for {ticker} as of {as_of}")


class DataRouterHistoricalLookup:
    """HistoricalLookup protocol implementation backed by DataRouter."""

    def __init__(self, router: DataRouter) -> None:
        self._router = router

    async def get_returns(self, ticker: str, days: int) -> np.ndarray:
        end = date.today().isoformat()
        start = (date.today() - timedelta(days=days + 10)).isoformat()
        hist = await self._router.get_daily_history(ticker, start, end)
        if hist is None or hist.empty:
            return np.array([])

        # Extract close prices (try common column names)
        if "close" in hist.columns:
            closes = hist["close"].tolist()
        elif "收盘" in hist.columns:
            closes = hist["收盘"].tolist()
        else:
            # Use the last numeric column as a best guess
            for col in reversed(hist.columns):
                try:
                    closes = [float(v) for v in hist[col].dropna()]
                    if len(closes) > 1:
                        break
                except (TypeError, ValueError):
                    continue
            else:
                return np.array([])

        prices = np.array([float(c) for c in closes], dtype=np.float64)
        if len(prices) < 2:
            return np.array([])
        return np.log(prices[1:] / prices[:-1])


class DataRouterSectorLookup:
    """SectorLookup protocol implementation backed by DataRouter.

    Uses financial indicators (行业/industry column) to determine sector.
    """

    def __init__(self, router: DataRouter) -> None:
        self._router = router

    async def get(self, ticker: str) -> str | None:
        try:
            df = await self._router.get_financial_indicators(ticker)
            if df is not None and not df.empty:
                row = df.iloc[0]
                sec = row.get("行业", row.get("industry", None))
                if sec is not None and str(sec).strip():
                    return str(sec).strip()
        except Exception:
            pass
        return None
