"""Unit tests for tools/api: derived metrics, TTM / Altman Z, price history widening,
and cluster-aware financial metrics.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from valor.tools import api as api_module
from valor.tools.api import (
    _compute_altman_z,
    _compute_derived_metrics,
    _compute_ttm,
    _compute_ttm_any,
    _extract_extended_balance_sheet_fields,
    _extract_extended_income_fields,
    _safe_div,
)


# ---------------------------------------------------------------------------
# _safe_div
# ---------------------------------------------------------------------------

def test_safe_div_normal():
    assert _safe_div(10.0, 5.0) == 2.0


def test_safe_div_zero_denominator():
    assert _safe_div(10.0, 0.0) == 0.0


def test_safe_div_none_denominator():
    assert _safe_div(10.0, None) == 0.0


# ---------------------------------------------------------------------------
# _compute_derived_metrics
# ---------------------------------------------------------------------------

def test_adj_debt_to_asset_strips_prepayments():
    """剔除预收款的资产负债率 = (负债-预收)/(资产-预收)."""
    latest = {
        "total_liabilities": 80,
        "total_assets": 100,
        "advance_from_customers": 20,
    }
    derived = _compute_derived_metrics(latest, {})
    # (80-20)/(100-20) = 60/80 = 0.75
    assert abs(derived["adj_debt_to_asset"] - 0.75) < 1e-6


def test_net_debt_to_equity():
    """净负债率 = (有息负债-货币资金)/净资产."""
    latest = {
        "short_term_loan": 30,
        "long_term_loan": 40,
        "bonds_payable": 10,
        "monetary_capital": 20,
        "total_equity": 60,
    }
    derived = _compute_derived_metrics(latest, {})
    # (30+40+10-20)/60 = 60/60 = 1.0
    assert abs(derived["net_debt_to_equity"] - 1.0) < 1e-6


def test_cash_to_short_debt():
    latest = {"monetary_capital": 50, "short_term_loan": 40}
    derived = _compute_derived_metrics(latest, {})
    assert abs(derived["cash_to_short_debt"] - 1.25) < 1e-6


def test_inventory_turnover_trend():
    """存货周转率 = 营业成本/平均存货, trend 判断用 _prev."""
    latest = {"operating_cost": 120, "inventory": 30}
    prev = {"inventory": 20}
    derived = _compute_derived_metrics(latest, prev)
    # 平均存货 = (30+20)/2 = 25, 周转率 = 120/25 = 4.8
    assert abs(derived["inventory_turnover"] - 4.8) < 1e-6


def test_ocf_to_net_profit():
    latest = {"operating_cash_flow": 80, "net_income": 100}
    derived = _compute_derived_metrics(latest, {})
    assert abs(derived["ocf_to_net_profit"] - 0.8) < 1e-6


def test_free_cash_flow():
    """FCF = OCF - capex."""
    latest = {"operating_cash_flow": 100, "capital_expenditure": 30}
    derived = _compute_derived_metrics(latest, {})
    assert derived["free_cash_flow"] == 70


def test_capex_to_ocf():
    latest = {"operating_cash_flow": 100, "capital_expenditure": 30}
    derived = _compute_derived_metrics(latest, {})
    assert abs(derived["capex_to_ocf"] - 0.3) < 1e-6


def test_asset_turnover_trend():
    latest = {"operating_revenue": 200, "total_assets": 100}
    prev = {"operating_revenue": 150, "total_assets": 100}
    derived = _compute_derived_metrics(latest, prev)
    # 当期 200/100=2.0, 上期 150/100=1.5
    assert abs(derived["asset_turnover"] - 2.0) < 1e-6
    assert abs(derived["asset_turnover_prev"] - 1.5) < 1e-6


def test_capex_to_depreciation():
    """资本支出/折旧摊销."""
    latest = {"capital_expenditure": 30, "depreciation_and_amortization": 100}
    derived = _compute_derived_metrics(latest, {})
    assert abs(derived["capex_to_depreciation"] - 0.3) < 1e-6


def test_receivable_to_revenue():
    """应收账款/营业收入."""
    latest = {"accounts_receivable": 50, "operating_revenue": 200}
    derived = _compute_derived_metrics(latest, {})
    assert abs(derived["receivable_to_revenue"] - 0.25) < 1e-6


def test_sales_expense_ratio():
    latest = {"sales_expense": 30, "operating_revenue": 200}
    derived = _compute_derived_metrics(latest, {})
    assert abs(derived["sales_expense_ratio"] - 0.15) < 1e-6


def test_gross_margin():
    latest = {"operating_revenue": 200, "operating_cost": 120}
    derived = _compute_derived_metrics(latest, {})
    # (200-120)/200 = 0.4
    assert abs(derived["gross_margin"] - 0.4) < 1e-6


def test_gross_margin_prev():
    latest = {"operating_revenue": 200, "operating_cost": 120}
    prev = {"operating_revenue": 150, "operating_cost": 100}
    derived = _compute_derived_metrics(latest, prev)
    # (150-100)/150 = 0.3333...
    assert abs(derived["gross_margin_prev"] - 0.333333333) < 1e-6


def test_empty_input_returns_empty():
    assert _compute_derived_metrics({}, {}) == {}


def test_none_prev_handled():
    """prev=None 应与 {} 等价."""
    latest = {"operating_revenue": 200, "total_assets": 100}
    derived = _compute_derived_metrics(latest, None)
    assert abs(derived["asset_turnover"] - 2.0) < 1e-6
    assert "asset_turnover_prev" not in derived


def test_division_by_zero_protected():
    """除零保护: 所有比率字段在分母为零时不崩溃."""
    latest = {
        "total_liabilities": 80,
        "total_assets": 0,
        "total_equity": 0,
        "short_term_loan": 0,
        "operating_revenue": 0,
        "operating_cost": 0,
        "net_income": 0,
        "operating_cash_flow": 0,
        "depreciation_and_amortization": 0,
    }
    derived = _compute_derived_metrics(latest, {})
    # 不应崩溃, 所有比率应为 0 或不存在
    assert isinstance(derived, dict)
    for k, v in derived.items():
        if k in ("free_cash_flow",):
            continue  # 非比率字段
        assert isinstance(v, (int, float)), f"{k}={v} should be numeric"


# ---------------------------------------------------------------------------
# _extract_extended_balance_sheet_fields
# ---------------------------------------------------------------------------

def test_extract_balance_sheet_fields():
    df = pd.DataFrame(
        [
            {
                "负债合计": 1e11,
                "资产总计": 2e11,
                "所有者权益合计": 1e11,
                "预收款项": 1e10,
                "存货": 5e10,
                "应收账款": 3e10,
                "短期借款": 2e10,
                "长期借款": 3e10,
                "应付债券": 1e10,
                "货币资金": 4e10,
            }
        ]
    )
    result = _extract_extended_balance_sheet_fields(df, 0)
    assert result["total_liabilities"] == 1e11
    assert result["total_assets"] == 2e11
    assert result["total_equity"] == 1e11
    assert result["advance_from_customers"] == 1e10
    assert result["inventory"] == 5e10
    assert result["accounts_receivable"] == 3e10
    assert result["short_term_loan"] == 2e10
    assert result["long_term_loan"] == 3e10
    assert result["bonds_payable"] == 1e10
    assert result["monetary_capital"] == 4e10


def test_extract_balance_sheet_alt_names():
    """测试备选字段名 (合同负债, 资产合计, 股东权益合计)."""
    df = pd.DataFrame(
        [
            {
                "负债总计": 1e11,
                "资产合计": 2e11,
                "股东权益合计": 1e11,
                "合同负债": 1e10,
            }
        ]
    )
    result = _extract_extended_balance_sheet_fields(df, 0)
    assert result["total_liabilities"] == 1e11
    assert result["total_assets"] == 2e11
    assert result["total_equity"] == 1e11
    assert result["advance_from_customers"] == 1e10


def test_extract_balance_sheet_empty_df():
    result = _extract_extended_balance_sheet_fields(pd.DataFrame(), 0)
    assert result == {}


def test_extract_balance_sheet_none_df():
    result = _extract_extended_balance_sheet_fields(None, 0)
    assert result == {}


def test_extract_balance_sheet_oob_index():
    """idx 越界返回空."""
    df = pd.DataFrame([{"负债合计": 1e11}])
    result = _extract_extended_balance_sheet_fields(df, 5)
    assert result == {}


# ---------------------------------------------------------------------------
# _extract_extended_income_fields
# ---------------------------------------------------------------------------

def test_extract_income_fields():
    df = pd.DataFrame(
        [
            {
                "营业成本": 1e11,
                "销售费用": 1e10,
                "营业总收入": 2e11,
                "净利润": 3e10,
            }
        ]
    )
    result = _extract_extended_income_fields(df, 0)
    assert result["operating_cost"] == 1e11
    assert result["sales_expense"] == 1e10
    assert result["operating_revenue"] == 2e11
    assert result["net_income"] == 3e10


def test_extract_income_alt_names():
    """测试备选字段名 (营业总成本, 营业收入)."""
    df = pd.DataFrame(
        [
            {
                "营业总成本": 1e11,
                "营业收入": 2e11,
            }
        ]
    )
    result = _extract_extended_income_fields(df, 0)
    assert result["operating_cost"] == 1e11
    assert result["operating_revenue"] == 2e11


def test_extract_income_empty_df():
    result = _extract_extended_income_fields(pd.DataFrame(), 0)
    assert result == {}


def test_extract_income_none_df():
    result = _extract_extended_income_fields(None, 0)
    assert result == {}


# ---------------------------------------------------------------------------
# _compute_ttm
# ---------------------------------------------------------------------------

def _make_report_df(dates_values: list[tuple[str, float]]) -> pd.DataFrame:
    """Build a minimal report DataFrame with 报告日 and 营业总收入 columns."""
    return pd.DataFrame(
        [{"报告日": d, "营业总收入": v} for d, v in dates_values]
    )


def test_ttm_annual_report_returns_as_is():
    """年报(12月)直接返回年报值,不需要 TTM 计算。"""
    df = _make_report_df([
        ("2025-12-31", 1720e8),
        ("2025-09-30", 1309e8),
        ("2025-06-30", 910e8),
        ("2025-03-31", 514e8),
    ])
    assert abs(_compute_ttm(df, "营业总收入", 0) - 1720e8) < 1e-6


def test_ttm_q1_uses_prior_year_annual_minus_prior_year_q1():
    """Q1 TTM = 当期Q1 + (上年年报 - 上年Q1)。

    模拟茅台 2026Q1: 547 + (1720 - 514) = 1753 亿。
    """
    df = _make_report_df([
        ("2026-03-31", 547e8),
        ("2025-12-31", 1720e8),
        ("2025-09-30", 1309e8),
        ("2025-06-30", 910e8),
        ("2025-03-31", 514e8),
        ("2024-12-31", 1741e8),
    ])
    ttm = _compute_ttm(df, "营业总收入", 0)
    expected = 547e8 + (1720e8 - 514e8)
    assert abs(ttm - expected) < 1e-6


def test_ttm_q3_uses_9m_ytd_plus_prior_year_residual():
    """Q3 TTM = 当期9M + (上年年报 - 上年9M)。"""
    df = _make_report_df([
        ("2025-09-30", 1309e8),
        ("2024-12-31", 1741e8),
        ("2024-09-30", 1250e8),
    ])
    ttm = _compute_ttm(df, "营业总收入", 0)
    expected = 1309e8 + (1741e8 - 1250e8)
    assert abs(ttm - expected) < 1e-6


def test_ttm_fallback_annualizes_ytd_when_prior_year_missing():
    """无上年同期数据时降级为 YTD 按月份年化(Q1×4)。"""
    df = _make_report_df([
        ("2026-03-31", 547e8),
        ("2025-12-31", 1720e8),
        # 缺 2025-03-31
    ])
    ttm = _compute_ttm(df, "营业总收入", 0)
    # Q1 (3月) -> ×4
    assert abs(ttm - 547e8 * 4) < 1e-6


def test_ttm_h1_fallback_uses_x2():
    """H1 (6月) 降级年化 ×2。"""
    df = _make_report_df([
        ("2026-06-30", 910e8),
    ])
    ttm = _compute_ttm(df, "营业总收入", 0)
    assert abs(ttm - 910e8 * 2) < 1e-6


def test_ttm_returns_zero_for_empty_df():
    assert _compute_ttm(pd.DataFrame(), "营业总收入", 0) == 0.0


def test_ttm_returns_zero_for_missing_field():
    """字段不存在时返回 0,不抛异常。"""
    df = _make_report_df([("2025-12-31", 1720e8)])
    assert _compute_ttm(df, "不存在字段", 0) == 0.0


# ---------------------------------------------------------------------------
# _compute_ttm_any
# ---------------------------------------------------------------------------

def test_ttm_any_tries_multiple_fields():
    """多候选字段名,用第一个存在的非零值。"""
    df = pd.DataFrame([
        {"报告日": "2025-12-31", "字段A": 100e8, "字段B": 200e8},
    ])
    assert abs(_compute_ttm_any(df, ["字段B"], 0) - 200e8) < 1e-6
    assert abs(_compute_ttm_any(df, ["字段A", "字段B"], 0) - 100e8) < 1e-6


def test_ttm_any_skips_missing_fields():
    df = pd.DataFrame([
        {"报告日": "2025-12-31", "字段B": 200e8},
    ])
    assert abs(_compute_ttm_any(df, ["字段A", "字段B"], 0) - 200e8) < 1e-6


# ---------------------------------------------------------------------------
# _compute_altman_z
# ---------------------------------------------------------------------------

def test_altman_z_known_values():
    """用茅台近似数据验证 Altman Z 计算。

    X1=0.7285, X2=0.6850, X3=0.469, X4=42.6, X5=0.547
    Z = 0.012*0.7285 + 0.014*0.6850 + 0.033*0.469 + 0.006*42.6 + 0.999*0.547
      ≈ 0.836
    """
    z = _compute_altman_z(
        working_capital=2330e8,
        total_assets=3199e8,
        retained_earnings=2191e8,
        ebit=1500e8,
        market_cap=16500e8,
        total_liabilities=387e8,
        revenue=1753e8,
    )
    assert 0.7 < z < 1.0


def test_altman_z_returns_zero_when_no_assets():
    """总资产为 0 时返回 0,避免除零。"""
    assert _compute_altman_z(
        working_capital=100, total_assets=0, retained_earnings=50,
        ebit=30, market_cap=1000, total_liabilities=200, revenue=500,
    ) == 0.0


def test_altman_z_handles_zero_liabilities():
    """总负债为 0 时 X4=0,不抛异常。"""
    z = _compute_altman_z(
        working_capital=100, total_assets=500, retained_earnings=200,
        ebit=50, market_cap=1000, total_liabilities=0, revenue=300,
    )
    # X4 = 0, other terms contribute
    assert z > 0


# ---------------------------------------------------------------------------
# get_price_history widen-range behavior
# ---------------------------------------------------------------------------

def _make_kline_df(symbol: str, dates: list[str], base_price: float = 6.0) -> pd.DataFrame:
    """Build a minimal kline df matching get_price_history_df output schema."""
    n = len(dates)
    return pd.DataFrame({
        "symbol": [symbol] * n,
        "adjust_flag": ["qfq"] * n,
        "date": pd.to_datetime(dates),
        "open": [base_price] * n,
        "high": [base_price + 0.5] * n,
        "low": [base_price - 0.2] * n,
        "close": [base_price + 0.2] * n,
        "volume": [100000] * n,
        "amount": [base_price * 100000] * n,
        "amplitude": [10.0] * n,
        "pct_change": [0.02] * n,
        "change_amount": [0.1] * n,
        "turnover": [0.01] * n,
    })


def test_widen_range_trims_back_to_original_window():
    """First fetch returns <120 rows -> widen to 730d; result must be masked
    back to the original [start, end] window the caller requested."""
    original_start = "2026-06-19"
    original_end = "2026-07-18"

    # First call: 20 trading days within the original 1-month window
    first_dates = list(pd.bdate_range("2026-06-19", "2026-07-14").strftime("%Y-%m-%d"))
    df_short = _make_kline_df("601728", first_dates)

    # Second call (widen): ~480 trading days across 2 years
    widen_dates = list(pd.bdate_range("2024-07-18", "2026-07-18").strftime("%Y-%m-%d"))
    df_wide = _make_kline_df("601728", widen_dates)

    with patch.object(api_module, "get_cache_refresh_flag", return_value=False), \
         patch.object(api_module, "get_price_history_df",
                      side_effect=[df_short, df_wide]) as mock_fetch:
        result = api_module.get_price_history("601728", original_start, original_end)

    # Widen must have triggered (two calls)
    assert mock_fetch.call_count == 2

    # Result must be trimmed back to the original window
    assert not result.empty
    assert result["date"].min() >= pd.Timestamp(original_start)
    assert result["date"].max() <= pd.Timestamp(original_end)
    # 1 month of trading days is ~22, definitely not 480+
    assert len(result) < 60, f"expected trimmed result, got {len(result)} rows"


def test_no_widen_when_enough_data():
    """When first fetch returns >=120 rows, widen must NOT trigger and the
    result must not be trimmed (caller gets exactly what was fetched)."""
    original_start = "2025-10-01"
    original_end = "2026-07-18"

    enough_dates = list(pd.bdate_range(original_start, original_end).strftime("%Y-%m-%d"))
    assert len(enough_dates) >= 120, "fixture should have enough rows"
    df_enough = _make_kline_df("601728", enough_dates)

    with patch.object(api_module, "get_cache_refresh_flag", return_value=False), \
         patch.object(api_module, "get_price_history_df",
                      return_value=df_enough) as mock_fetch:
        result = api_module.get_price_history("601728", original_start, original_end)

    # No widen -> only one fetch
    assert mock_fetch.call_count == 1
    # No trimming -> all rows returned
    assert len(result) == len(df_enough)


# ---------------------------------------------------------------------------
# Cluster-aware get_financial_metrics
# ---------------------------------------------------------------------------

def test_financial_cluster_adds_bank_special(monkeypatch: pytest.MonkeyPatch) -> None:
    """financial 集群追加银行专项指标."""
    monkeypatch.setattr(api_module, "get_valuation_indicator",
                        lambda s: {"pe_ttm": 5, "pb": 0.8, "market_cap": 1e10, "price": 10})
    monkeypatch.setattr(api_module, "get_financial_indicators",
                        lambda **kw: __import__("pandas").DataFrame(
                            {"日期": ["2024-01-01"], "净资产收益率(%)": [12]}))
    monkeypatch.setattr(api_module, "get_financial_report",
                        lambda s, t, **kw: __import__("pandas").DataFrame())
    monkeypatch.setattr(api_module, "get_dividend_yield", lambda s, p: 0.03)
    monkeypatch.setattr(api_module, "get_market_snapshot", lambda **kw: {})
    monkeypatch.setattr(api_module, "get_cache_refresh_flag", lambda *a, **kw: False)
    monkeypatch.setattr(api_module, "get_bank_special_indicators",
                        lambda s: {"net_interest_margin": 0.016, "non_performing_loan_ratio": 0.012})
    metrics = api_module.get_financial_metrics("600036", cluster_hint="financial")
    assert metrics[0]["net_interest_margin"] == 0.016
    assert metrics[0]["non_performing_loan_ratio"] == 0.012


def test_cyclical_cluster_adds_pb_percentile(monkeypatch: pytest.MonkeyPatch) -> None:
    """cyclical_resource 集群追加 PB 分位数."""
    monkeypatch.setattr(api_module, "get_valuation_indicator",
                        lambda s: {"pe_ttm": 8, "pb": 1.2, "market_cap": 1e10, "price": 20})
    monkeypatch.setattr(api_module, "get_financial_indicators",
                        lambda **kw: __import__("pandas").DataFrame(
                            {"日期": ["2024-01-01"], "净资产收益率(%)": [10]}))
    monkeypatch.setattr(api_module, "get_financial_report",
                        lambda s, t, **kw: __import__("pandas").DataFrame())
    monkeypatch.setattr(api_module, "get_dividend_yield", lambda s, p: 0.05)
    monkeypatch.setattr(api_module, "get_market_snapshot", lambda **kw: {})
    monkeypatch.setattr(api_module, "get_cache_refresh_flag", lambda *a, **kw: False)
    monkeypatch.setattr(api_module, "get_history_pb",
                        lambda s, years=5: [("2024-01-01", 1.0), ("2024-02-01", 1.5), ("2024-03-01", 2.0)])
    monkeypatch.setattr(api_module, "_compute_pb_percentile", lambda series, cur: 0.2)
    metrics = api_module.get_financial_metrics("601088", cluster_hint="cyclical_resource")
    assert metrics[0]["pb_percentile_5y"] == 0.2


def test_no_cluster_hint_returns_base_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    """无 cluster_hint 不追加专属指标."""
    monkeypatch.setattr(api_module, "get_valuation_indicator",
                        lambda s: {"pe_ttm": 10, "pb": 1.5, "market_cap": 1e10, "price": 15})
    monkeypatch.setattr(api_module, "get_financial_indicators",
                        lambda **kw: __import__("pandas").DataFrame(
                            {"日期": ["2024-01-01"], "净资产收益率(%)": [15]}))
    monkeypatch.setattr(api_module, "get_financial_report",
                        lambda s, t, **kw: __import__("pandas").DataFrame())
    monkeypatch.setattr(api_module, "get_dividend_yield", lambda s, p: 0.02)
    monkeypatch.setattr(api_module, "get_market_snapshot", lambda **kw: {})
    monkeypatch.setattr(api_module, "get_cache_refresh_flag", lambda *a, **kw: False)
    metrics = api_module.get_financial_metrics("600519")
    assert "net_interest_margin" not in metrics[0]
    assert "pb_percentile_5y" not in metrics[0]