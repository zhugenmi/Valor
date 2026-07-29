"""Unit tests for fundamentals_agent - config-driven cluster evaluation.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

import json

from valor.agents.fundamentals import fundamentals_agent


def _make_state(cluster="conglomerate", metrics=None, industry="综合"):
    """Build a minimal AgentState for fundamentals_agent tests.

    Defaults to conglomerate cluster with a realistic bullish metrics set.
    """
    default_metrics = {
        "return_on_equity": 0.20,
        "net_margin": 0.25,
        "operating_margin": 0.18,
        "revenue_growth": 0.15,
        "earnings_growth": 0.12,
        "book_value_growth": 0.10,
        "current_ratio": 2.0,
        "debt_to_equity": 0.3,
        "free_cash_flow_per_share": 5.0,
        "earnings_per_share": 6.0,
        "pe_ratio": 20.0,
        "price_to_book": 2.5,
        "price_to_sales": 3.0,
    }
    return {
        "messages": [],
        "data": {
            "financial_metrics": [metrics if metrics is not None else default_metrics],
            "cluster": cluster,
            "industry": industry,
        },
        "metadata": {"show_reasoning": False},
    }


def test_fundamentals_output_includes_risk_flags():
    """fundamentals_agent output must include a 'risk_flags' field (list)."""
    result = fundamentals_agent(_make_state())
    content = json.loads(result["messages"][0].content)

    assert "risk_flags" in content
    assert isinstance(content["risk_flags"], list)


def test_fundamentals_risk_flags_defaults_to_empty():
    """If no risk flags are computed, risk_flags defaults to empty list."""
    result = fundamentals_agent(_make_state())
    content = json.loads(result["messages"][0].content)

    assert content.get("risk_flags") == []


# ---------------------------------------------------------------------------
# Task 8: config-driven cluster engine tests
# ---------------------------------------------------------------------------


def test_conglomerate_outputs_5_dimensions():
    """conglomerate cluster outputs 5 dimensions (regression anchor)."""
    metrics = {
        "return_on_equity": 0.18, "net_margin": 0.25, "operating_margin": 0.20,
        "revenue_growth": 0.15, "earnings_growth": 0.12, "book_value_growth": 0.10,
        "current_ratio": 2.0, "debt_to_equity": 0.3, "free_cash_flow_per_share": 1.0,
        "earnings_per_share": 0.8, "pe_ratio": 20, "price_to_book": 2, "price_to_sales": 3,
        "dividend_yield": 0.05, "payout_ratio": 0.4,
    }
    result = fundamentals_agent(_make_state("conglomerate", metrics))
    msg = json.loads(result["messages"][0].content)
    assert "industry_profile" in msg
    assert msg["industry_profile"]["cluster"] == "conglomerate"
    assert len(msg["reasoning"]) == 5
    assert set(msg["reasoning"].keys()) == {
        "profitability", "growth", "financial_health", "valuation", "shareholder_return",
    }


def test_financial_cluster_outputs_5_dimensions_with_bank_metrics():
    """financial cluster outputs 5 dimensions but with bank-specific metrics."""
    metrics = {
        "return_on_equity": 0.12, "net_interest_margin": 0.016,
        "revenue_growth": 0.08,
        "non_performing_loan_ratio": 0.012, "provision_coverage": 2.5,
        "core_tier1_capital_ratio": 0.095,
        "price_to_book": 0.8, "dividend_yield": 0.04,
    }
    result = fundamentals_agent(_make_state("financial", metrics, industry="银行"))
    msg = json.loads(result["messages"][0].content)
    assert msg["industry_profile"]["cluster"] == "financial"
    assert msg["industry_profile"]["valuation_method"] == "pb"
    # financial_health dimension includes bank-specific metrics
    health = msg["reasoning"]["financial_health"]
    assert health["weight"] == 0.35
    assert any("不良" in m["label"] for m in health["metrics"])


def test_tmt_cluster_has_4_dimensions_no_shareholder_return():
    """TMT removes shareholder_return, only 4 dimensions."""
    metrics = {
        "gross_margin": 0.4, "gross_margin_prev": 0.35, "net_margin": 0.15,
        "revenue_growth": 0.20, "earnings_growth": 0.18, "r_and_d_to_revenue": 0.12,
        "ocf_to_net_profit": 0.9, "current_ratio": 2.0,
        "pe_ratio": 25,
    }
    result = fundamentals_agent(_make_state("tmt", metrics, industry="计算机"))
    msg = json.loads(result["messages"][0].content)
    assert "shareholder_return" not in msg["reasoning"]
    assert len(msg["reasoning"]) == 4


def test_missing_cluster_defaults_to_conglomerate():
    """state without cluster field defaults to conglomerate."""
    state = {
        "messages": [], "data": {"financial_metrics": [{}]}, "metadata": {"show_reasoning": False},
    }
    result = fundamentals_agent(state)
    msg = json.loads(result["messages"][0].content)
    assert msg["industry_profile"]["cluster"] == "conglomerate"


# ---------------------------------------------------------------------------
# Task 12: conglomerate regression assertions
# ---------------------------------------------------------------------------


def test_conglomerate_signal_matches_legacy_logic():
    """conglomerate cluster output matches pre-refactor fundamentals.py logic.

    Before refactor: 5 dimensions X 3 metrics each, majority vote,
    bullish > bearish -> bullish.
    After refactor: conglomerate config + weighted vote (weights all 0.20,
    equivalent to majority voting).
    """
    # All metrics pass -> bullish, confidence = 100%
    metrics = {
        "return_on_equity": 0.18, "net_margin": 0.25, "operating_margin": 0.20,
        "revenue_growth": 0.15, "earnings_growth": 0.12, "book_value_growth": 0.11,
        "current_ratio": 2.0, "debt_to_equity": 0.3, "free_cash_flow_per_share": 1.0,
        "earnings_per_share": 0.8, "pe_ratio": 20, "price_to_book": 2, "price_to_sales": 3,
        "dividend_yield": 0.05, "payout_ratio": 0.4,
    }
    result = fundamentals_agent(_make_state("conglomerate", metrics))
    msg = json.loads(result["messages"][0].content)
    assert msg["signal"] == "bullish"
    # 5 dimensions all bullish, overall = 1.0, confidence = 100%
    assert msg["confidence"] == "100%"


def test_conglomerate_all_fail_returns_bearish():
    """All metrics fail -> bearish signal."""
    metrics = {
        "return_on_equity": 0.01, "net_margin": 0.01, "operating_margin": 0.01,
        "revenue_growth": -0.1, "earnings_growth": -0.1, "book_value_growth": -0.1,
        "current_ratio": 0.5, "debt_to_equity": 0.9, "free_cash_flow_per_share": 0.1,
        "earnings_per_share": 0.1, "pe_ratio": 100, "price_to_book": 10, "price_to_sales": 20,
        "dividend_yield": 0.001, "payout_ratio": 0,
    }
    result = fundamentals_agent(_make_state("conglomerate", metrics))
    msg = json.loads(result["messages"][0].content)
    assert msg["signal"] == "bearish"