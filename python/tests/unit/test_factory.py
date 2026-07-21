"""Tests for build_data_router factory."""

from __future__ import annotations

import pytest

from valor.adapters.data.factory import build_data_router
from valor.adapters.data.router import DataRouter


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
