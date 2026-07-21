"""Tests for unit_conversion helpers."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from valor.adapters.data.unit_conversion import (
    KLINE_UNIFIED_COLUMNS,
    build_unified_kline_df,
    compute_amplitude,
    pct_to_decimal,
    to_shares,
    to_yuan,
    validate_unified_kline,
)


class TestToShares:
    def test_basic_conversion(self):
        assert to_shares(1) == 100.0
        assert to_shares(100) == 10000.0

    def test_none(self):
        assert to_shares(None) == 0.0

    def test_nan(self):
        assert to_shares(float("nan")) == 0.0

    def test_string_numeric(self):
        assert to_shares("100") == 10000.0

    def test_invalid_string(self):
        assert to_shares("abc") == 0.0

    def test_negative(self):
        assert to_shares(-5) == -500.0


class TestToYuan:
    def test_basic_conversion(self):
        assert to_yuan(1) == 1000.0
        assert to_yuan(1000) == 1_000_000.0

    def test_none(self):
        assert to_yuan(None) == 0.0

    def test_nan(self):
        assert to_yuan(float("nan")) == 0.0


class TestPctToDecimal:
    def test_basic_conversion(self):
        assert pct_to_decimal(5.0) == pytest.approx(0.05)
        assert pct_to_decimal(100) == pytest.approx(1.0)

    def test_none(self):
        assert pct_to_decimal(None) == 0.0

    def test_nan(self):
        assert pct_to_decimal(float("nan")) == 0.0


class TestComputeAmplitude:
    def test_basic(self):
        assert compute_amplitude(11.0, 9.0, 10.0) == pytest.approx(20.0)

    def test_zero_preclose(self):
        assert compute_amplitude(11.0, 9.0, 0.0) == 0.0

    def test_negative_preclose(self):
        assert compute_amplitude(11.0, 9.0, -10.0) == 0.0


class TestBuildUnifiedKlineDf:
    def test_columns_match_schema(self):
        df = build_unified_kline_df(
            symbol="600519",
            adjust="qfq",
            date=["2026-07-17"],
            open=[10.0],
            high=[10.5],
            low=[9.9],
            close=[10.2],
            volume=[10000],
            amount=[102000],
        )
        assert list(df.columns) == list(KLINE_UNIFIED_COLUMNS)

    def test_optional_columns_default_to_zero(self):
        df = build_unified_kline_df(
            symbol="600519",
            adjust="",
            date=["2026-07-17"],
            open=[10.0],
            high=[10.5],
            low=[9.9],
            close=[10.2],
            volume=[10000],
            amount=[102000],
        )
        assert df["amplitude"].iloc[0] == 0.0
        assert df["pct_change"].iloc[0] == 0.0
        assert df["change_amount"].iloc[0] == 0.0
        assert df["turnover"].iloc[0] == 0.0

    def test_date_is_datetime(self):
        df = build_unified_kline_df(
            symbol="600519",
            adjust="qfq",
            date=["2026-07-17"],
            open=[10.0],
            high=[10.5],
            low=[9.9],
            close=[10.2],
            volume=[10000],
            amount=[102000],
        )
        assert pd.api.types.is_datetime64_any_dtype(df["date"])

    def test_nan_values_filled_to_zero(self):
        df = build_unified_kline_df(
            symbol="600519",
            adjust="qfq",
            date=["2026-07-17"],
            open=[float("nan")],
            high=[10.5],
            low=[9.9],
            close=[10.2],
            volume=[10000],
            amount=[102000],
        )
        assert not math.isnan(df["open"].iloc[0])
        assert df["open"].iloc[0] == 0.0


class TestValidateUnifiedKline:
    def test_valid_df(self):
        df = build_unified_kline_df(
            symbol="600519", adjust="qfq",
            date=["2026-07-17"], open=[10.0], high=[10.5], low=[9.9],
            close=[10.2], volume=[10000], amount=[102000],
        )
        assert validate_unified_kline(df) == []

    def test_missing_column(self):
        df = pd.DataFrame({
            "symbol": ["600519"], "adjust_flag": [""], "date": ["2026-07-17"],
            "open": [10.0], "high": [10.5], "low": [9.9], "close": [10.2],
            "volume": [10000], "amount": [102000],
            "amplitude": [0.0], "pct_change": [0.0], "change_amount": [0.0],
            # turnover missing
        })
        issues = validate_unified_kline(df)
        assert any("missing" in i for i in issues)

    def test_extra_column(self):
        df = build_unified_kline_df(
            symbol="600519", adjust="qfq",
            date=["2026-07-17"], open=[10.0], high=[10.5], low=[9.9],
            close=[10.2], volume=[10000], amount=[102000],
        )
        df["extra"] = 1
        issues = validate_unified_kline(df)
        assert any("extra" in i for i in issues)
