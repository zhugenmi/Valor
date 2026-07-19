"""Tests for akshare K-line fallback (_fetch_kline_via_akshare).

Verifies column mapping from akshare's Chinese schema to the same schema
produced by _prepare_history_frame, so fallback rows can be cached in the
same baostock_history_k table without downstream changes.
"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from valor.adapters.data.akshare_cache import _fetch_kline_via_akshare


def _fake_akshare_df() -> pd.DataFrame:
    """Mimic ak.stock_zh_a_hist output schema."""
    return pd.DataFrame(
        {
            "日期": ["2026-07-15", "2026-07-16", "2026-07-17"],
            "开盘": [10.0, 10.5, 10.4],
            "收盘": [10.2, 10.4, 10.6],
            "最高": [10.5, 10.6, 10.8],
            "最低": [9.9, 10.3, 10.3],
            "成交量": [100000, 120000, 90000],
            "成交额": [1020000, 1248000, 954000],
            "振幅": [6.0, 2.9, 4.8],
            "涨跌幅": [2.0, 1.96, 1.92],
            "涨跌额": [0.2, 0.2, 0.2],
            "换手率": [1.0, 1.2, 0.9],
        }
    )


def test_fetch_kline_via_akshare_maps_columns_to_internal_schema():
    """akshare Chinese columns map to internal English schema."""
    with patch("valor.adapters.data.akshare_cache.ak.stock_zh_a_hist",
               return_value=_fake_akshare_df()):
        df = _fetch_kline_via_akshare(
            symbol="000858",
            start_date="2026-07-15",
            end_date="2026-07-17",
            adjust="qfq",
        )

    expected_columns = {
        "symbol", "adjust_flag", "date", "open", "high", "low", "close",
        "volume", "amount", "amplitude", "pct_change", "change_amount", "turnover",
    }
    assert set(df.columns) == expected_columns
    assert len(df) == 3
    assert df["symbol"].iloc[0] == "000858"
    assert df["adjust_flag"].iloc[0] == "qfq"
    # pct_change should be decimal (0.02), not percent (2.0)
    assert df["pct_change"].iloc[0] == pytest.approx(0.02)
    # turnover should be decimal (0.01), not percent (1.0)
    assert df["turnover"].iloc[0] == pytest.approx(0.01)
    # amplitude stays as percent (matches _prepare_history_frame)
    assert df["amplitude"].iloc[0] == pytest.approx(6.0)
    # date column is datetime
    assert pd.api.types.is_datetime64_any_dtype(df["date"])


def test_fetch_kline_via_akshare_returns_empty_when_akshare_fails():
    """When ak.stock_zh_a_hist returns None/empty, fallback returns empty df."""
    with patch("valor.adapters.data.akshare_cache.ak.stock_zh_a_hist",
               return_value=pd.DataFrame()):
        df = _fetch_kline_via_akshare(
            symbol="000858",
            start_date="2026-07-15",
            end_date="2026-07-17",
            adjust="qfq",
        )
    assert df.empty


def test_fetch_kline_via_akshare_returns_empty_on_exception():
    """When ak.stock_zh_a_hist raises, _call_with_retry returns None -> empty df."""
    with patch("valor.adapters.data.akshare_cache.ak.stock_zh_a_hist",
               side_effect=RuntimeError("akshare down")):
        df = _fetch_kline_via_akshare(
            symbol="000858",
            start_date="2026-07-15",
            end_date="2026-07-17",
            adjust="qfq",
        )
    assert df.empty


def test_fetch_kline_via_akshare_handles_missing_columns_gracefully():
    """If akshare returns a subset of columns, missing fields default to 0."""
    partial = pd.DataFrame(
        {
            "日期": ["2026-07-15"],
            "开盘": [10.0],
            "收盘": [10.2],
            "最高": [10.5],
            "最低": [9.9],
            "成交量": [100000],
        }
    )
    with patch("valor.adapters.data.akshare_cache.ak.stock_zh_a_hist",
               return_value=partial):
        df = _fetch_kline_via_akshare(
            symbol="000858",
            start_date="2026-07-15",
            end_date="2026-07-15",
            adjust="qfq",
        )
    assert len(df) == 1
    assert df["close"].iloc[0] == pytest.approx(10.2)
    # amount/turnover/amplitude absent -> default 0
    assert df["amount"].iloc[0] == 0
    assert df["turnover"].iloc[0] == 0