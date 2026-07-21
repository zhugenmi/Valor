"""Tests for DataRouter field-level fallback behavior."""

import pandas as pd
import pytest

from valor.adapters.data.router import DataRouter


class FakeAdapter:
    def __init__(self, name: str, fail_methods: set[str] | None = None) -> None:
        self.name = name
        self.fail_methods = fail_methods or set()
        self.calls: list[tuple[str, tuple]] = []

    async def get_realtime_quote(self, ticker: str) -> pd.DataFrame:
        self.calls.append(("get_realtime_quote", (ticker,)))
        if "get_realtime_quote" in self.fail_methods:
            raise RuntimeError(f"{self.name} failed")
        return pd.DataFrame({"close": [10.0], "source": [self.name]})

    async def get_daily_history(
        self, ticker: str, start: str, end: str
    ) -> pd.DataFrame:
        self.calls.append(("get_daily_history", (ticker, start, end)))
        if "get_daily_history" in self.fail_methods:
            raise RuntimeError(f"{self.name} failed")
        return pd.DataFrame({"close": [10.0], "source": [self.name]})

    async def get_financial_indicators(self, ticker: str) -> pd.DataFrame:
        return pd.DataFrame()

    async def get_news(self, ticker: str, limit: int = 20) -> pd.DataFrame:
        return pd.DataFrame()


@pytest.mark.asyncio
async def test_router_uses_first_source_on_success():
    primary = FakeAdapter("akshare")
    secondary = FakeAdapter("baostock")
    router = DataRouter(
        primary=primary,
        fallbacks_by_method={
            "get_realtime_quote": ["baostock"],
            "get_daily_history": ["baostock"],
        },
        sources={"akshare": primary, "baostock": secondary},
    )
    df = await router.get_realtime_quote("600519")
    assert df["source"].iloc[0] == "akshare"
    assert len(secondary.calls) == 0


@pytest.mark.asyncio
async def test_router_falls_back_on_failure():
    primary = FakeAdapter("akshare", fail_methods={"get_realtime_quote"})
    secondary = FakeAdapter("baostock")
    router = DataRouter(
        primary=primary,
        fallbacks_by_method={"get_realtime_quote": ["baostock"]},
        sources={"akshare": primary, "baostock": secondary},
    )
    df = await router.get_realtime_quote("600519")
    assert df["source"].iloc[0] == "baostock"


@pytest.mark.asyncio
async def test_router_raises_when_all_sources_fail():
    primary = FakeAdapter("akshare", fail_methods={"get_realtime_quote"})
    secondary = FakeAdapter("baostock", fail_methods={"get_realtime_quote"})
    router = DataRouter(
        primary=primary,
        fallbacks_by_method={"get_realtime_quote": ["baostock"]},
        sources={"akshare": primary, "baostock": secondary},
    )
    with pytest.raises(RuntimeError, match="all sources failed"):
        await router.get_realtime_quote("600519")


@pytest.mark.asyncio
async def test_router_three_source_fallback_chain():
    """BaoStock -> AkShare -> Tushare chain: first two fail, third succeeds."""
    primary = FakeAdapter("baostock", fail_methods={"get_daily_history"})
    akshare = FakeAdapter("akshare", fail_methods={"get_daily_history"})
    tushare = FakeAdapter("tushare")
    router = DataRouter(
        primary=primary,
        fallbacks_by_method={"get_daily_history": ["akshare", "tushare"]},
        sources={"baostock": primary, "akshare": akshare, "tushare": tushare},
    )
    df = await router.get_daily_history("600519", "2026-07-15", "2026-07-17")
    assert df["source"].iloc[0] == "tushare"
    # Both primary and first fallback were attempted
    assert len(primary.calls) == 1
    assert len(akshare.calls) == 1
    assert len(tushare.calls) == 1


@pytest.mark.asyncio
async def test_router_fallback_chain_stops_at_first_success():
    """If primary succeeds, fallbacks are not called."""
    primary = FakeAdapter("baostock")
    akshare = FakeAdapter("akshare")
    tushare = FakeAdapter("tushare")
    router = DataRouter(
        primary=primary,
        fallbacks_by_method={"get_daily_history": ["akshare", "tushare"]},
        sources={"baostock": primary, "akshare": akshare, "tushare": tushare},
    )
    df = await router.get_daily_history("600519", "2026-07-15", "2026-07-17")
    assert df["source"].iloc[0] == "baostock"
    assert len(akshare.calls) == 0
    assert len(tushare.calls) == 0
