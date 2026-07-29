"""Unit tests for get_r_and_d_expense fallback chain.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
import pandas as pd
import pytest

from valor.adapters.data import akshare_cache
from valor.adapters.data.akshare_cache import get_r_and_d_expense


def _make_income_df(rd: float, revenue: float, capitalized: float = 0) -> pd.DataFrame:
    """构造利润表 DataFrame, 模拟 get_financial_report 返回格式."""
    data = {
        "研发费用": [rd],
        "营业总收入": [revenue],
        "报告日": ["2024-12-31"],
    }
    if capitalized > 0:
        data["研发资本化金额"] = [capitalized]
    return pd.DataFrame(data)


def test_r_and_d_expense_returns_dict_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """正常返回研发投入数据."""
    df = _make_income_df(rd=1.5e9, revenue=3e10, capitalized=3e8)
    monkeypatch.setattr(
        akshare_cache,
        "get_financial_report",
        lambda symbol, report_type, ttl_seconds=0, force_refresh=False: df,
    )
    result = get_r_and_d_expense("600276")
    assert "r_and_d_to_revenue" in result
    assert abs(result["r_and_d_to_revenue"] - 0.05) < 0.001
    assert "r_and_d_capitalization_rate" in result
    assert abs(result["r_and_d_capitalization_rate"] - 0.2) < 0.001


def test_r_and_d_expense_no_capitalized(monkeypatch: pytest.MonkeyPatch) -> None:
    """无资本化金额时只返回 r_and_d_to_revenue."""
    df = _make_income_df(rd=1e9, revenue=2e10)
    monkeypatch.setattr(
        akshare_cache,
        "get_financial_report",
        lambda symbol, report_type, ttl_seconds=0, force_refresh=False: df,
    )
    result = get_r_and_d_expense("000651")
    assert "r_and_d_to_revenue" in result
    assert "r_and_d_capitalization_rate" not in result


def test_r_and_d_expense_returns_empty_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """异常时返回空 dict."""
    def boom(symbol, report_type, ttl_seconds=0, force_refresh=False):
        raise RuntimeError("api error")

    monkeypatch.setattr(akshare_cache, "get_financial_report", boom)
    result = get_r_and_d_expense("600276")
    assert result == {}


def test_r_and_d_expense_returns_empty_on_empty_df(monkeypatch: pytest.MonkeyPatch) -> None:
    """返回空 DataFrame 时返回空 dict."""
    monkeypatch.setattr(
        akshare_cache,
        "get_financial_report",
        lambda symbol, report_type, ttl_seconds=0, force_refresh=False: pd.DataFrame(),
    )
    result = get_r_and_d_expense("600276")
    assert result == {}


def test_r_and_d_expense_returns_empty_on_none_df(monkeypatch: pytest.MonkeyPatch) -> None:
    """返回 None 时返回空 dict."""
    monkeypatch.setattr(
        akshare_cache,
        "get_financial_report",
        lambda symbol, report_type, ttl_seconds=0, force_refresh=False: None,
    )
    result = get_r_and_d_expense("600276")
    assert result == {}


def test_r_and_d_expense_handles_zero_revenue(monkeypatch: pytest.MonkeyPatch) -> None:
    """营收为 0 时跳过比率计算."""
    df = _make_income_df(rd=1e9, revenue=0)
    monkeypatch.setattr(
        akshare_cache,
        "get_financial_report",
        lambda symbol, report_type, ttl_seconds=0, force_refresh=False: df,
    )
    result = get_r_and_d_expense("600276")
    assert result == {}