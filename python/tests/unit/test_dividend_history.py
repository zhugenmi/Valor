"""Unit tests for get_dividend_history and _compute_dividend_years.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
import pandas as pd
import pytest

from valor.adapters.data import akshare_cache
from valor.adapters.data.akshare_cache import (
    get_dividend_history,
    _compute_dividend_years,
)


def test_compute_dividend_years_counts_consecutive():
    history = [
        ("2020", 0.3),
        ("2021", 0.4),
        ("2022", 0.5),
        ("2023", 0.6),
        ("2024", 0.7),
    ]
    assert _compute_dividend_years(history) == 5


def test_compute_dividend_years_empty():
    assert _compute_dividend_years([]) == 0


def test_get_dividend_history_fallback_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(symbol):
        raise RuntimeError("api error")

    monkeypatch.setattr(akshare_cache.ak, "stock_dividend_cninfo", boom)
    assert get_dividend_history("600036") == []


def test_get_dividend_history_returns_records(monkeypatch: pytest.MonkeyPatch) -> None:
    """正常返回分红记录."""
    df = pd.DataFrame({
        "年度": ["2020", "2021", "2022", "2023", "2024"],
        "分红金额": [0.3, 0.4, 0.5, 0.6, 0.7],
    })

    def fake_dividend(symbol):
        return df

    monkeypatch.setattr(akshare_cache.ak, "stock_dividend_cninfo", fake_dividend)
    result = get_dividend_history("600036", years=3)
    assert len(result) == 3
    assert result == [("2022", 0.5), ("2023", 0.6), ("2024", 0.7)]


def test_get_dividend_history_empty_df_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """API 返回空 DataFrame."""
    monkeypatch.setattr(
        akshare_cache.ak,
        "stock_dividend_cninfo",
        lambda symbol: pd.DataFrame(),
    )
    assert get_dividend_history("600036") == []


def test_get_dividend_history_none_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """API 返回 None."""
    monkeypatch.setattr(
        akshare_cache.ak,
        "stock_dividend_cninfo",
        lambda symbol: None,
    )
    assert get_dividend_history("600036") == []