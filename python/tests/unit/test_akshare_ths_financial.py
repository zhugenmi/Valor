"""Tests for AkShare THS (同花顺) financial report fallback.

When 新浪 (Sina) report endpoint fails, ``get_financial_report`` falls back
to THS endpoints (``stock_financial_benefit_ths`` etc.). THS data is parsed
from "亿"/"万" strings and field-mapped to match Sina's schema so both
sources can land in the same ``stock_financial_report_sina`` table.
"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from valor.adapters.data import akshare_cache as ac_module
from valor.adapters.data.akshare_cache import (
    COL_CODE,
    COL_REPORT_DATE,
    COL_REPORT_TYPE,
    _fetch_financial_report_ths,
    _parse_ths_amount,
    get_financial_report,
)
from valor.adapters.data.sqlite_cache import AkshareSQLiteCache


# ---------------------------------------------------------------------------
# _parse_ths_amount
# ---------------------------------------------------------------------------


class TestParseThsAmount:
    def test_yi(self):
        assert _parse_ths_amount("281.54亿") == pytest.approx(281.54e8)

    def test_wan(self):
        assert _parse_ths_amount("5931.07万") == pytest.approx(5931.07e4)

    def test_false_string(self):
        assert _parse_ths_amount("False") == 0.0

    def test_dash(self):
        assert _parse_ths_amount("--") == 0.0

    def test_empty(self):
        assert _parse_ths_amount("") == 0.0

    def test_none(self):
        assert _parse_ths_amount(None) == 0.0

    def test_plain_number(self):
        assert _parse_ths_amount("1.16") == pytest.approx(1.16)

    def test_negative_yi(self):
        assert _parse_ths_amount("-1.16亿") == pytest.approx(-1.16e8)


# ---------------------------------------------------------------------------
# _fetch_financial_report_ths
# ---------------------------------------------------------------------------


def _fake_ths_income_df() -> pd.DataFrame:
    """Mimic stock_financial_benefit_ths output."""
    return pd.DataFrame({
        "报告期": ["2026-03-31", "2025-12-31"],
        "报表核心指标": ["x", "y"],
        "*净利润": ["281.54亿", "853.10亿"],
        "*营业总收入": ["547.03亿", "1720.54亿"],
        "一、营业总收入": ["547.03亿", "1720.54亿"],
        "三、营业利润": ["375.37亿", "1148.09亿"],
        "五、净利润": ["281.54亿", "853.10亿"],
    })


def _fake_ths_debt_df() -> pd.DataFrame:
    """Mimic stock_financial_debt_ths output."""
    return pd.DataFrame({
        "报告期": ["2026-03-31"],
        "流动资产合计": ["2715.25亿"],
        "流动负债合计": ["367.16亿"],
        "资产合计": ["3199.19亿"],
        "负债合计": ["384.56亿"],
    })


def _fake_ths_cash_df() -> pd.DataFrame:
    """Mimic stock_financial_cash_ths output."""
    return pd.DataFrame({
        "报告期": ["2026-03-31"],
        "经营活动产生的现金流量净额": ["100.00亿"],
        "购建固定资产、无形资产和其他长期资产支付的现金": ["-5.00亿"],
        "固定资产折旧、油气资产折耗、生产性生物资产折旧": ["3.00亿"],
    })


def test_fetch_income_renames_prefixed_fields():
    with patch.object(ac_module.ak, "stock_financial_benefit_ths",
                      return_value=_fake_ths_income_df()):
        df = _fetch_financial_report_ths("600519", "利润表")

    assert COL_CODE in df.columns
    assert COL_REPORT_TYPE in df.columns
    assert COL_REPORT_DATE in df.columns
    # Prefixed THS fields renamed to Sina equivalents
    assert "营业总收入" in df.columns
    assert "营业利润" in df.columns
    assert "净利润" in df.columns
    # Original prefixed names should NOT remain
    assert "一、营业总收入" not in df.columns
    # Data parsed from "亿" string to float
    assert df["净利润"].iloc[0] == pytest.approx(281.54e8)
    # Report date normalized to YYYY-MM-DD
    assert df[COL_REPORT_DATE].iloc[0] == "2026-03-31"


def test_fetch_debt_preserves_field_names():
    with patch.object(ac_module.ak, "stock_financial_debt_ths",
                      return_value=_fake_ths_debt_df()):
        df = _fetch_financial_report_ths("600519", "资产负债表")

    # THS debt fields match Sina names exactly - no rename needed
    assert "流动资产合计" in df.columns
    assert "流动负债合计" in df.columns
    assert df["流动资产合计"].iloc[0] == pytest.approx(2715.25e8)


def test_fetch_cash_preserves_field_names():
    with patch.object(ac_module.ak, "stock_financial_cash_ths",
                      return_value=_fake_ths_cash_df()):
        df = _fetch_financial_report_ths("600519", "现金流量表")

    assert "经营活动产生的现金流量净额" in df.columns
    assert df["经营活动产生的现金流量净额"].iloc[0] == pytest.approx(100.00e8)


def test_fetch_returns_empty_for_unknown_report_type():
    df = _fetch_financial_report_ths("600519", "未知报表")
    assert df.empty


def test_fetch_returns_empty_on_akshare_failure():
    with patch.object(ac_module.ak, "stock_financial_benefit_ths",
                      side_effect=RuntimeError("network")):
        df = _fetch_financial_report_ths("600519", "利润表")
    assert df.empty


# ---------------------------------------------------------------------------
# get_financial_report: Sina -> THS fallback chain
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_cache(monkeypatch: pytest.MonkeyPatch, tmp_path) -> AkshareSQLiteCache:
    cache = AkshareSQLiteCache(tmp_path / "test.db")
    monkeypatch.setattr(ac_module, "cache", cache)
    return cache


def _force_refresh(monkeypatch: pytest.MonkeyPatch):
    """Bypass report calendar so need_fetch is always True."""
    monkeypatch.setattr(
        "valor.adapters.data.report_calendar.should_refresh_reports",
        lambda latest: True,
    )


def test_get_financial_report_falls_back_to_ths(temp_cache, monkeypatch):
    """Sina returns empty -> THS fills the gap -> data cached."""
    _force_refresh(monkeypatch)

    with patch.object(ac_module.ak, "stock_financial_report_sina",
                      return_value=pd.DataFrame()), \
         patch.object(ac_module.ak, "stock_financial_benefit_ths",
                      return_value=_fake_ths_income_df()):
        df = get_financial_report("600519", "利润表", force_refresh=True)

    assert not df.empty
    assert len(df) == 2
    # THS data should land in the same Sina cache table
    cached = temp_cache.fetch_records(
        table="stock_financial_report_sina",
        filters={COL_CODE: "600519", COL_REPORT_TYPE: "利润表"},
    )
    assert len(cached) == 2
    # Field name should be the Sina-style key (no THS prefix)
    assert "净利润" in cached[0]


def test_both_sources_fail_returns_cached(temp_cache, monkeypatch):
    """Sina + THS both fail -> return stale cache."""
    _force_refresh(monkeypatch)

    # Pre-seed cache with a row
    seed = pd.DataFrame([{
        COL_CODE: "600519",
        COL_REPORT_TYPE: "利润表",
        COL_REPORT_DATE: "2025-12-31",
        "净利润": 853.10e8,
    }])
    temp_cache.upsert_records(
        table="stock_financial_report_sina",
        records=seed.to_dict("records"),
        key_columns=[COL_CODE, COL_REPORT_TYPE, COL_REPORT_DATE],
    )

    # force_refresh=False so cached rows are loaded; should_refresh_reports
    # is mocked True so the fetch is still attempted.
    with patch.object(ac_module.ak, "stock_financial_report_sina",
                      return_value=pd.DataFrame()), \
         patch.object(ac_module.ak, "stock_financial_benefit_ths",
                      return_value=pd.DataFrame()):
        df = get_financial_report("600519", "利润表", force_refresh=False)

    assert not df.empty
    assert len(df) == 1
    assert str(df[COL_REPORT_DATE].iloc[0])[:10] == "2025-12-31"


def test_both_sources_fail_no_cache_returns_empty(temp_cache, monkeypatch):
    """Sina + THS both fail, no cache -> empty DataFrame."""
    _force_refresh(monkeypatch)

    with patch.object(ac_module.ak, "stock_financial_report_sina",
                      return_value=pd.DataFrame()), \
         patch.object(ac_module.ak, "stock_financial_benefit_ths",
                      return_value=pd.DataFrame()):
        df = get_financial_report("600519", "利润表", force_refresh=True)

    assert df.empty


def test_sina_success_skips_ths(temp_cache, monkeypatch):
    """When Sina returns data, THS is not called."""
    _force_refresh(monkeypatch)

    sina_df = pd.DataFrame({
        "报告日": ["2026-03-31"],
        "营业总收入": [547.0e8],
        "净利润": [281.54e8],
    })

    with patch.object(ac_module.ak, "stock_financial_report_sina",
                      return_value=sina_df) as mock_sina, \
         patch.object(ac_module.ak, "stock_financial_benefit_ths",
                      side_effect=AssertionError("THS should not be called")):
        df = get_financial_report("600519", "利润表", force_refresh=True)

    assert not df.empty
    mock_sina.assert_called_once()
