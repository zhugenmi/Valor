"""Tests for TushareClient, TokenBucket rate limiter, and TushareAdapter.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from valor.adapters.data.tushare_adapter import TushareAdapter
from valor.adapters.data.tushare_client import (
    DEFAULT_BURST,
    DEFAULT_RATE,
    TokenBucket,
    TushareClient,
    TushareUnavailable,
    _normalize_date,
)
from valor.adapters.data.unit_conversion import KLINE_UNIFIED_COLUMNS


class TestTokenBucket:
    def test_initial_burst_allows_acquires(self):
        bucket = TokenBucket(rate=10.0, burst=5)
        # Burst of 5 should allow 5 immediate acquires
        results = [bucket.acquire() for _ in range(5)]
        assert all(results)
        # 6th should fail (bucket empty)
        assert bucket.acquire() is False

    def test_refill_after_time(self):
        bucket = TokenBucket(rate=100.0, burst=1)
        assert bucket.acquire() is True
        assert bucket.acquire() is False
        # Wait long enough for ~1 token at 100/s
        time.sleep(0.05)
        assert bucket.acquire() is True

    def test_wait_and_acquire_blocks_then_succeeds(self):
        bucket = TokenBucket(rate=100.0, burst=1)
        assert bucket.acquire() is True
        # Should block briefly then succeed
        start = time.monotonic()
        ok = bucket.wait_and_acquire(timeout=0.5)
        elapsed = time.monotonic() - start
        assert ok is True
        assert elapsed >= 0.005  # at least some wait

    def test_wait_and_acquire_timeout(self):
        bucket = TokenBucket(rate=0.01, burst=1)
        assert bucket.acquire() is True
        # rate is 0.01/s = 100s per token, so timeout=0.1 should fail
        ok = bucket.wait_and_acquire(timeout=0.1)
        assert ok is False

    def test_invalid_rate_raises(self):
        with pytest.raises(ValueError):
            TokenBucket(rate=0, burst=1)

    def test_invalid_burst_raises(self):
        with pytest.raises(ValueError):
            TokenBucket(rate=1.0, burst=0)

    def test_default_rate_matches_50_per_minute(self):
        assert DEFAULT_RATE == pytest.approx(50.0 / 60.0)

    def test_default_burst_is_10(self):
        assert DEFAULT_BURST == 10


class TestTsCodeConversion:
    def test_shanghai_6_prefix(self):
        assert TushareClient.to_ts_code("600519") == "600519.SH"

    def test_shanghai_9_prefix(self):
        assert TushareClient.to_ts_code("900952") == "900952.SH"

    def test_shenzhen_0_prefix(self):
        assert TushareClient.to_ts_code("000858") == "000858.SZ"

    def test_shenzhen_3_prefix(self):
        assert TushareClient.to_ts_code("300750") == "300750.SZ"

    def test_already_has_suffix_passes_through(self):
        assert TushareClient.to_ts_code("600519.SH") == "600519.SH"

    def test_from_ts_code(self):
        assert TushareClient.from_ts_code("600519.SH") == "600519"
        assert TushareClient.from_ts_code("000858.SZ") == "000858"


class TestNormalizeDate:
    def test_dash_format(self):
        assert _normalize_date("2026-07-17") == "20260717"

    def test_compact_format(self):
        assert _normalize_date("20260717") == "20260717"

    def test_empty(self):
        assert _normalize_date("") == ""


class TestTushareClientInit:
    def test_no_token_unavailable(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
        client = TushareClient(token=None)
        assert client.available is False

    def test_empty_token_unavailable(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
        client = TushareClient(token="")
        assert client.available is False

    def test_valid_token_initializes(self, monkeypatch: pytest.MonkeyPatch):
        mock_pro = MagicMock()
        with patch("tushare.set_token") as mock_set_token, \
             patch("tushare.pro_api", return_value=mock_pro):
            client = TushareClient(token="fake-token")
        assert client.available is True
        mock_set_token.assert_called_once_with("fake-token")


class TestQueryDaily:
    def _build_client(self) -> TushareClient:
        with patch("tushare.set_token"), \
             patch("tushare.pro_api", return_value=MagicMock()):
            return TushareClient(token="fake-token")

    def test_query_daily_calls_pro_daily(self, monkeypatch: pytest.MonkeyPatch):
        client = self._build_client()
        fake_df = pd.DataFrame({
            "ts_code": ["600519.SH"],
            "trade_date": ["20260717"],
            "open": [10.0], "high": [10.5], "low": [9.9], "close": [10.2],
            "pre_close": [10.0], "change": [0.2], "pct_chg": [2.0],
            "vol": [1000], "amount": [1020],
        })
        client._pro.daily = MagicMock(return_value=fake_df)
        df = client.query_daily("600519.SH", "2026-07-17", "2026-07-17")
        assert len(df) == 1
        client._pro.daily.assert_called_once_with(
            ts_code="600519.SH", start_date="20260717", end_date="20260717"
        )

    def test_query_daily_returns_empty_on_exception(self):
        client = self._build_client()
        client._pro.daily = MagicMock(side_effect=RuntimeError("network"))
        df = client.query_daily("600519.SH", "2026-07-17", "2026-07-17")
        assert df.empty

    def test_query_daily_returns_empty_on_none(self):
        client = self._build_client()
        client._pro.daily = MagicMock(return_value=None)
        df = client.query_daily("600519.SH", "2026-07-17", "2026-07-17")
        assert df.empty

    def test_query_daily_unavailable_raises(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
        client = TushareClient(token=None)
        with pytest.raises(TushareUnavailable):
            client.query_daily("600519.SH", "2026-07-17", "2026-07-17")


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