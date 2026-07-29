"""Unit tests for derived metrics computation and extended field extraction.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

import pandas as pd
from valor.tools.api import (
    _compute_derived_metrics,
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