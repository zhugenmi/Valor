"""Tests for TushareClient and TokenBucket rate limiter."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from valor.adapters.data.tushare_client import (
    DEFAULT_BURST,
    DEFAULT_RATE,
    TokenBucket,
    TushareClient,
    TushareUnavailable,
    _normalize_date,
)


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
