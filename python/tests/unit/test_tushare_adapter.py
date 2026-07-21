"""Tests for TushareAdapter field mapping and unit conversion."""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from valor.adapters.data.tushare_adapter import TushareAdapter
from valor.adapters.data.unit_conversion import KLINE_UNIFIED_COLUMNS


def _fake_tushare_daily_df() -> pd.DataFrame:
    """Mimic Tushare pro.daily() output for two trading days."""
    return pd.DataFrame({
        "ts_code": ["600519.SH", "600519.SH"],
        "trade_date": ["20260716", "20260717"],
        "open": [10.0, 10.4],
        "high": [10.5, 10.8],
        "low": [9.9, 10.3],
        "close": [10.2, 10.6],
        "pre_close": [10.0, 10.2],
        "change": [0.2, 0.4],
        "pct_chg": [2.0, 3.921568627],
        "vol": [1000.0, 1200.0],          # 手
        "amount": [1020.0, 1272.0],        # 千元
    })


def _make_adapter_with_mock_client() -> TushareAdapter:
    adapter = TushareAdapter()
    adapter._client = MagicMock()
    adapter._client.available = True
    adapter._client.query_daily = MagicMock(return_value=_fake_tushare_daily_df())
    return adapter


@pytest.mark.asyncio
async def test_adapter_get_daily_history_maps_fields():
    adapter = _make_adapter_with_mock_client()
    df = await adapter.get_daily_history("600519", "2026-07-16", "2026-07-17")

    assert list(df.columns) == list(KLINE_UNIFIED_COLUMNS)
    assert len(df) == 2
    # Sorted ascending by trade_date
    assert df["date"].iloc[0] < df["date"].iloc[1]


@pytest.mark.asyncio
async def test_adapter_volume_conversion_hands_to_shares():
    """Tushare vol=1000 (手) -> volume=100000 (股)."""
    adapter = _make_adapter_with_mock_client()
    df = await adapter.get_daily_history("600519", "2026-07-16", "2026-07-17")
    assert df["volume"].iloc[0] == pytest.approx(1000.0 * 100)
    assert df["volume"].iloc[1] == pytest.approx(1200.0 * 100)


@pytest.mark.asyncio
async def test_adapter_amount_conversion_thousands_to_yuan():
    """Tushare amount=1020 (千元) -> amount=1020000 (元)."""
    adapter = _make_adapter_with_mock_client()
    df = await adapter.get_daily_history("600519", "2026-07-16", "2026-07-17")
    assert df["amount"].iloc[0] == pytest.approx(1020.0 * 1000)
    assert df["amount"].iloc[1] == pytest.approx(1272.0 * 1000)


@pytest.mark.asyncio
async def test_adapter_pct_chg_conversion_to_decimal():
    """Tushare pct_chg=2.0 (%) -> pct_change=0.02 (decimal)."""
    adapter = _make_adapter_with_mock_client()
    df = await adapter.get_daily_history("600519", "2026-07-16", "2026-07-17")
    assert df["pct_change"].iloc[0] == pytest.approx(0.02)


@pytest.mark.asyncio
async def test_adapter_amplitude_calculation():
    """amplitude = (high - low) / preclose * 100."""
    adapter = _make_adapter_with_mock_client()
    df = await adapter.get_daily_history("600519", "2026-07-16", "2026-07-17")
    # Row 0: (10.5 - 9.9) / 10.0 * 100 = 6.0
    assert df["amplitude"].iloc[0] == pytest.approx(6.0)


@pytest.mark.asyncio
async def test_adapter_change_amount_passthrough():
    """Tushare change (元) -> change_amount (元), no conversion."""
    adapter = _make_adapter_with_mock_client()
    df = await adapter.get_daily_history("600519", "2026-07-16", "2026-07-17")
    assert df["change_amount"].iloc[0] == pytest.approx(0.2)


@pytest.mark.asyncio
async def test_adapter_turnover_zero_when_missing():
    """Tushare daily doesn't provide turnover -> default 0.0."""
    adapter = _make_adapter_with_mock_client()
    df = await adapter.get_daily_history("600519", "2026-07-16", "2026-07-17")
    assert (df["turnover"] == 0.0).all()


@pytest.mark.asyncio
async def test_adapter_adjust_flag_empty_for_unadjusted():
    """Tushare daily is unadjusted; adjust_flag must be empty string."""
    adapter = _make_adapter_with_mock_client()
    df = await adapter.get_daily_history("600519", "2026-07-16", "2026-07-17")
    assert (df["adjust_flag"] == "").all()


@pytest.mark.asyncio
async def test_adapter_empty_response_returns_empty_df():
    adapter = _make_adapter_with_mock_client()
    adapter._client.query_daily = MagicMock(return_value=pd.DataFrame())
    df = await adapter.get_daily_history("600519", "2026-07-16", "2026-07-17")
    assert df.empty
    assert list(df.columns) == list(KLINE_UNIFIED_COLUMNS)


@pytest.mark.asyncio
async def test_adapter_unavailable_raises(monkeypatch: pytest.MonkeyPatch):
    """Without TUSHARE_TOKEN, get_daily_history raises TushareUnavailable."""
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    from valor.adapters.data.tushare_client import TushareUnavailable

    adapter = TushareAdapter()
    with pytest.raises(TushareUnavailable):
        await adapter.get_daily_history("600519", "2026-07-16", "2026-07-17")


@pytest.mark.asyncio
async def test_adapter_realtime_quote_not_implemented():
    adapter = _make_adapter_with_mock_client()
    with pytest.raises(NotImplementedError):
        await adapter.get_realtime_quote("600519")


@pytest.mark.asyncio
async def test_adapter_financial_indicators_not_implemented():
    adapter = _make_adapter_with_mock_client()
    with pytest.raises(NotImplementedError):
        await adapter.get_financial_indicators("600519")


@pytest.mark.asyncio
async def test_adapter_news_not_implemented():
    adapter = _make_adapter_with_mock_client()
    with pytest.raises(NotImplementedError):
        await adapter.get_news("600519")
