"""Tests for DataRouter field-level fallback behavior and build_data_router factory."""

from __future__ import annotations

import pandas as pd
import pytest

from valor.adapters.data.factory import build_data_router
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


def test_build_data_router_without_tushare_token(monkeypatch: pytest.MonkeyPatch):
    """Without TUSHARE_TOKEN, router has akshare + baostock only."""
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    router = build_data_router()
    assert isinstance(router, DataRouter)
    assert "akshare" in router._sources
    assert "baostock" in router._sources
    assert "tushare" not in router._sources
    assert router._fallbacks.get("get_daily_history") == ["baostock"]


def test_build_data_router_with_tushare_token(monkeypatch: pytest.MonkeyPatch):
    """With TUSHARE_TOKEN set, router registers tushare as third fallback."""
    monkeypatch.setenv("TUSHARE_TOKEN", "fake-token")

    # Mock TushareClient so it doesn't actually call tushare SDK
    from unittest.mock import patch, MagicMock

    with patch("valor.adapters.data.tushare_adapter.TushareClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.available = True
        mock_client_cls.return_value = mock_client
        router = build_data_router()

    assert "tushare" in router._sources
    fallbacks = router._fallbacks.get("get_daily_history")
    assert fallbacks == ["baostock", "tushare"]


def test_build_data_router_skips_tushare_when_init_fails(monkeypatch: pytest.MonkeyPatch):
    """If TUSHARE_TOKEN is set but TushareClient init fails, tushare is skipped."""
    monkeypatch.setenv("TUSHARE_TOKEN", "fake-token")

    from unittest.mock import patch, MagicMock

    with patch("valor.adapters.data.tushare_adapter.TushareClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.available = False  # init failed
        mock_client_cls.return_value = mock_client
        router = build_data_router()

    # Tushare not registered because available=False
    assert "tushare" not in router._sources
    assert router._fallbacks.get("get_daily_history") == ["baostock"]