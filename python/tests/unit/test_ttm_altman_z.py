"""Unit tests for TTM (trailing twelve months) and Altman Z-score computation.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

import pandas as pd

from valor.tools.api import _compute_altman_z, _compute_ttm, _compute_ttm_any


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
