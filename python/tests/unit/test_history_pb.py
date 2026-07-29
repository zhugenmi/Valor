"""Unit tests for get_history_pb and _compute_pb_percentile.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
import pytest

from valor.adapters.data import akshare_cache
from valor.adapters.data.akshare_cache import get_history_pb, _compute_pb_percentile


def test_compute_pb_percentile_low_position():
    """当前 PB 在序列低端 -> 分位数低."""
    series = [("2024-01-01", 1.0), ("2024-02-01", 1.1), ("2024-03-01", 1.2),
              ("2024-04-01", 1.3), ("2024-05-01", 1.4)]
    # current 1.0 是最小值 -> 分位数 0.0
    pct = _compute_pb_percentile(series, current_pb=1.0)
    assert pct is not None
    assert pct < 0.1


def test_compute_pb_percentile_high_position():
    series = [("2024-01-01", 1.0), ("2024-02-01", 1.1), ("2024-03-01", 1.2),
              ("2024-04-01", 1.3), ("2024-05-01", 1.4)]
    pct = _compute_pb_percentile(series, current_pb=1.4)
    assert pct is not None
    assert pct > 0.9


def test_compute_pb_percentile_empty_series_returns_none():
    assert _compute_pb_percentile([], current_pb=1.0) is None


def test_compute_pb_percentile_single_point_returns_none():
    assert _compute_pb_percentile([("2024-01-01", 1.0)], current_pb=1.0) is None


def test_get_history_pb_fallback_to_empty_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(symbol, indicator, period):
        raise RuntimeError("api error")
    monkeypatch.setattr(akshare_cache.ak, "stock_zh_valuation_baidu", boom)
    result = get_history_pb("600036", years=5)
    assert result == []