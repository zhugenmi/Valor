"""Unit tests for get_bank_special_indicators fallback chain.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
import pytest

from valor.adapters.data import akshare_cache
from valor.adapters.data.akshare_cache import get_bank_special_indicators


def test_bank_special_returns_dict_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Level 1 成功返回银行专项指标."""
    fake_report = {
        "net_interest_margin": 0.015,
        "non_performing_loan_ratio": 0.012,
        "provision_coverage": 2.5,
        "core_tier1_capital_ratio": 0.095,
    }
    monkeypatch.setattr(
        akshare_cache,
        "_parse_bank_special_from_report",
        lambda symbol: fake_report,
    )
    result = get_bank_special_indicators("600036")
    assert result["net_interest_margin"] == 0.015
    assert result["non_performing_loan_ratio"] == 0.012
    assert result["provision_coverage"] == 2.5
    assert result["core_tier1_capital_ratio"] == 0.095


def test_bank_special_returns_empty_on_all_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    """全 fallback 失败返回空 dict."""
    monkeypatch.setattr(
        akshare_cache,
        "_parse_bank_special_from_report",
        lambda symbol: {},
    )
    monkeypatch.setattr(
        akshare_cache,
        "_online_search_metrics",
        lambda symbol, fields: {},
    )
    monkeypatch.setattr(
        akshare_cache,
        "_llm_estimate_metrics",
        lambda symbol, fields, hint: {},
    )
    result = get_bank_special_indicators("600036")
    assert result == {}


def test_bank_special_l1_exception_falls_through(monkeypatch: pytest.MonkeyPatch) -> None:
    """Level 1 抛异常时不死, 继续 fallback."""
    def boom(symbol):
        raise RuntimeError("parse error")

    monkeypatch.setattr(akshare_cache, "_parse_bank_special_from_report", boom)
    monkeypatch.setattr(
        akshare_cache,
        "_online_search_metrics",
        lambda symbol, fields: {"net_interest_margin": 0.016},
    )
    monkeypatch.setattr(
        akshare_cache,
        "_llm_estimate_metrics",
        lambda symbol, fields, hint: {},
    )
    result = get_bank_special_indicators("600036")
    assert result["net_interest_margin"] == 0.016


def test_bank_special_partial_missing_goes_to_l2(monkeypatch: pytest.MonkeyPatch) -> None:
    """L1 只返回部分指标, 剩余的走 L2/L3."""
    monkeypatch.setattr(
        akshare_cache,
        "_parse_bank_special_from_report",
        lambda symbol: {"net_interest_margin": 0.015},
    )
    monkeypatch.setattr(
        akshare_cache,
        "_online_search_metrics",
        lambda symbol, fields: {
            "non_performing_loan_ratio": 0.013,
            "provision_coverage": 2.6,
        },
    )
    monkeypatch.setattr(
        akshare_cache,
        "_llm_estimate_metrics",
        lambda symbol, fields, hint: {
            "core_tier1_capital_ratio": 0.098,
        },
    )
    result = get_bank_special_indicators("600036")
    assert result["net_interest_margin"] == 0.015
    assert result["non_performing_loan_ratio"] == 0.013
    assert result["provision_coverage"] == 2.6
    assert result["core_tier1_capital_ratio"] == 0.098