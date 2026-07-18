"""Tests for DataRouter-backed portfolio lookup adapters.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pandas as pd
import pytest

from valor.portfolio.adapters import (
    DataRouterHistoricalLookup,
    DataRouterPriceLookup,
    DataRouterSectorLookup,
)


@pytest.mark.asyncio
async def test_price_lookup_realtime_success():
    """Price from realtime quote DataFrame (最新价 column)."""
    router = MagicMock()
    router.get_realtime_quote = AsyncMock(
        return_value=pd.DataFrame([{"代码": "600519", "最新价": 1750.20}])
    )
    lookup = DataRouterPriceLookup(router)
    price = await lookup.get("600519", date(2026, 7, 17))
    assert price == Decimal("1750.20")


@pytest.mark.asyncio
async def test_price_lookup_realtime_empty_falls_back():
    """Empty realtime quote triggers fallback to daily history close."""
    router = MagicMock()
    router.get_realtime_quote = AsyncMock(return_value=pd.DataFrame())
    router.get_daily_history = AsyncMock(
        return_value=pd.DataFrame([{"date": "2026-07-16", "close": 1700.0}])
    )
    lookup = DataRouterPriceLookup(router)
    price = await lookup.get("600519", date(2026, 7, 17))
    assert price == Decimal("1700.0")


@pytest.mark.asyncio
async def test_price_lookup_realtime_exception_falls_back():
    """Exception in realtime quote triggers fallback to daily history."""
    router = MagicMock()
    router.get_realtime_quote = AsyncMock(side_effect=RuntimeError("boom"))
    router.get_daily_history = AsyncMock(
        return_value=pd.DataFrame([{"date": "2026-07-16", "close": 1700.0}])
    )
    lookup = DataRouterPriceLookup(router)
    price = await lookup.get("600519", date(2026, 7, 17))
    assert price == Decimal("1700.0")


@pytest.mark.asyncio
async def test_price_lookup_no_data_raises():
    """No data at all raises ValueError."""
    router = MagicMock()
    router.get_realtime_quote = AsyncMock(return_value=pd.DataFrame())
    router.get_daily_history = AsyncMock(return_value=pd.DataFrame())
    lookup = DataRouterPriceLookup(router)
    with pytest.raises(ValueError, match="no price"):
        await lookup.get("600519", date(2026, 7, 17))


@pytest.mark.asyncio
async def test_price_lookup_fallback_column_close():
    """Fallback reads 'close' column from history DataFrame."""
    router = MagicMock()
    router.get_realtime_quote = AsyncMock(return_value=pd.DataFrame())
    router.get_daily_history = AsyncMock(
        return_value=pd.DataFrame({"close": [1680.0, 1700.0]})
    )
    lookup = DataRouterPriceLookup(router)
    price = await lookup.get("600519", date(2026, 7, 17))
    assert price == Decimal("1700.0")


@pytest.mark.asyncio
async def test_historical_lookup_returns_array():
    """get_returns returns log return array."""
    router = MagicMock()
    router.get_daily_history = AsyncMock(
        return_value=pd.DataFrame({"close": [10.0, 11.0, 10.5]})
    )
    lookup = DataRouterHistoricalLookup(router)
    rets = await lookup.get_returns("600519", 30)
    assert isinstance(rets, np.ndarray)
    assert len(rets) == 2  # 3 prices -> 2 returns


@pytest.mark.asyncio
async def test_historical_lookup_single_price_returns_empty():
    """Fewer than 2 prices returns empty array."""
    router = MagicMock()
    router.get_daily_history = AsyncMock(
        return_value=pd.DataFrame({"close": [10.0]})
    )
    lookup = DataRouterHistoricalLookup(router)
    rets = await lookup.get_returns("600519", 30)
    assert isinstance(rets, np.ndarray)
    assert len(rets) == 0


@pytest.mark.asyncio
async def test_historical_lookup_empty_dataframe():
    """Empty history returns empty array."""
    router = MagicMock()
    router.get_daily_history = AsyncMock(return_value=pd.DataFrame())
    lookup = DataRouterHistoricalLookup(router)
    rets = await lookup.get_returns("600519", 30)
    assert isinstance(rets, np.ndarray)
    assert len(rets) == 0


@pytest.mark.asyncio
async def test_historical_lookup_close_column():
    """get_returns uses 'close' column when present."""
    router = MagicMock()
    router.get_daily_history = AsyncMock(
        return_value=pd.DataFrame({"close": [10.0, 11.0, 12.0]})
    )
    lookup = DataRouterHistoricalLookup(router)
    rets = await lookup.get_returns("600519", 30)
    assert len(rets) == 2
    assert np.isclose(rets[0], np.log(11.0 / 10.0))


@pytest.mark.asyncio
async def test_historical_lookup_close_cn_column():
    """get_returns uses '收盘' (Chinese close) column."""
    router = MagicMock()
    router.get_daily_history = AsyncMock(
        return_value=pd.DataFrame({"收盘": [15.0, 16.0]})
    )
    lookup = DataRouterHistoricalLookup(router)
    rets = await lookup.get_returns("600519", 30)
    assert len(rets) == 1
    assert np.isclose(rets[0], np.log(16.0 / 15.0))


@pytest.mark.asyncio
async def test_historical_lookup_fallback_column():
    """get_returns falls back to last numeric column when 'close'/'收盘' missing."""
    router = MagicMock()
    router.get_daily_history = AsyncMock(
        return_value=pd.DataFrame({"price": [20.0, 21.0, 22.0]})
    )
    lookup = DataRouterHistoricalLookup(router)
    rets = await lookup.get_returns("600519", 30)
    assert len(rets) == 2


@pytest.mark.asyncio
async def test_historical_lookup_no_numeric_column():
    """get_returns returns empty when no column is parseable as float."""
    router = MagicMock()
    router.get_daily_history = AsyncMock(
        return_value=pd.DataFrame({"ticker": ["A", "B", "C"], "name": ["foo", "bar", "baz"]})
    )
    lookup = DataRouterHistoricalLookup(router)
    rets = await lookup.get_returns("600519", 30)
    assert isinstance(rets, np.ndarray)
    assert len(rets) == 0


@pytest.mark.asyncio
async def test_sector_lookup_exception_returns_none():
    """Exception in financial indicators returns None."""
    router = MagicMock()
    router.get_financial_indicators = AsyncMock(side_effect=RuntimeError("boom"))
    lookup = DataRouterSectorLookup(router)
    sec = await lookup.get("600519")
    assert sec is None


@pytest.mark.asyncio
async def test_sector_lookup_from_industry():
    """Sector from 行业 column in financial indicators."""
    router = MagicMock()
    router.get_financial_indicators = AsyncMock(
        return_value=pd.DataFrame([{"行业": "白酒", "市盈率": 30.5}])
    )
    lookup = DataRouterSectorLookup(router)
    sec = await lookup.get("600519")
    assert sec == "白酒"


@pytest.mark.asyncio
async def test_sector_lookup_fallback_industry():
    """Sector from 'industry' column if 行业 not present."""
    router = MagicMock()
    router.get_financial_indicators = AsyncMock(
        return_value=pd.DataFrame([{"industry": "Technology"}])
    )
    lookup = DataRouterSectorLookup(router)
    sec = await lookup.get("AAPL")
    assert sec == "Technology"


@pytest.mark.asyncio
async def test_sector_lookup_empty_returns_none():
    """Empty indicators returns None."""
    router = MagicMock()
    router.get_financial_indicators = AsyncMock(return_value=pd.DataFrame())
    lookup = DataRouterSectorLookup(router)
    sec = await lookup.get("600519")
    assert sec is None
