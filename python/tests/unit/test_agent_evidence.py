"""Tests for evidence field in rule-driven agents' output.

Verifies that technicals/fundamentals/valuation/risk_manager agents
include an ``evidence`` dict in their message_content, listing the
specific indicator values used to derive the signal. Downstream LLM
agents (bull_bear_debate, portfolio_manager) reference these values
in their prompts.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from __future__ import annotations

import json

from valor.agents.fundamentals import fundamentals_agent
from valor.agents.risk_manager import risk_management_agent
from valor.agents.technicals import technical_analyst_agent
from valor.agents.valuation import valuation_agent


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _make_financial_metrics() -> dict:
    return {
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
        "dividend_yield": 0.0693,
        "book_value_per_share": 32.98,
        "payout_ratio": 1.386,
    }


def _make_financial_line_items() -> list:
    return [
        {
            "net_income": 1_000_000_000,
            "depreciation_and_amortization": 200_000_000,
            "capital_expenditure": 150_000_000,
            "working_capital": 500_000_000,
            "free_cash_flow": 800_000_000,
        },
        {
            "net_income": 900_000_000,
            "depreciation_and_amortization": 180_000_000,
            "capital_expenditure": 140_000_000,
            "working_capital": 480_000_000,
            "free_cash_flow": 750_000_000,
        },
    ]


def _make_prices_records(n_days: int = 120) -> list:
    """Build a list of price dicts (state.data['prices'] format)."""
    records = []
    base_close = 10.0
    for i in range(n_days):
        records.append({
            "date": f"2026-01-{(i % 28) + 1:02d}" if i < 28 else f"2026-{(i // 28) + 2:02d}-{(i % 28) + 1:02d}",
            "open": base_close + i * 0.01,
            "high": base_close + i * 0.01 + 0.2,
            "low": base_close + i * 0.01 - 0.1,
            "close": base_close + i * 0.01,
            "volume": 10000 + i * 10,
        })
    return records


# ---------------------------------------------------------------------------
# fundamentals_agent evidence
# ---------------------------------------------------------------------------


def test_fundamentals_output_includes_evidence():
    state = {
        "messages": [],
        "data": {
            "ticker": "600519",
            "end_date": "2026-07-18",
            "portfolio": {"cash": 100000.0, "stock": 0},
            "financial_metrics": [_make_financial_metrics()],
        },
        "metadata": {"show_reasoning": False, "model": "openai"},
    }
    result = fundamentals_agent(state)
    content = json.loads(result["messages"][0].content)

    assert "evidence" in content
    assert isinstance(content["evidence"], dict)
    ev = content["evidence"]
    assert ev["return_on_equity"] == 0.20
    assert ev["net_margin"] == 0.25
    assert ev["revenue_growth"] == 0.15
    assert ev["pe_ratio"] == 20.0
    assert ev["price_to_book"] == 2.5
    assert ev["debt_to_equity"] == 0.3
    assert ev["current_ratio"] == 2.0
    assert ev["dividend_yield"] == 0.0693
    assert ev["book_value_per_share"] == 32.98
    assert ev["payout_ratio"] == 1.386


def test_fundamentals_evidence_handles_missing_fields():
    """Missing financial metrics should yield 0.0 in evidence, not raise."""
    state = {
        "messages": [],
        "data": {
            "ticker": "600519",
            "end_date": "2026-07-18",
            "portfolio": {"cash": 100000.0, "stock": 0},
            "financial_metrics": [{}],  # empty metrics
        },
        "metadata": {"show_reasoning": False, "model": "openai"},
    }
    result = fundamentals_agent(state)
    content = json.loads(result["messages"][0].content)

    assert "evidence" in content
    ev = content["evidence"]
    assert ev["return_on_equity"] == 0.0
    assert ev["pe_ratio"] == 0.0
    assert ev["dividend_yield"] == 0.0
    assert ev["book_value_per_share"] == 0.0
    assert ev["payout_ratio"] == 0.0


def test_fundamentals_dividend_signal_scoring_bullish():
    """股息率 >= 4% 应触发 bullish shareholder_return_signal."""
    metrics = _make_financial_metrics()
    metrics["dividend_yield"] = 0.0693  # 6.93% > 4%
    metrics["payout_ratio"] = 0.5  # 可持续
    state = {
        "messages": [],
        "data": {
            "ticker": "000858",
            "end_date": "2026-07-18",
            "portfolio": {"cash": 100000.0, "stock": 0},
            "financial_metrics": [metrics],
        },
        "metadata": {"show_reasoning": False, "model": "openai"},
    }
    result = fundamentals_agent(state)
    content = json.loads(result["messages"][0].content)

    assert "shareholder_return_signal" in content["reasoning"]
    sig = content["reasoning"]["shareholder_return_signal"]
    assert sig["signal"] == "bullish"
    assert "6.93%" in sig["details"]


def test_fundamentals_dividend_signal_scoring_bearish():
    """股息率 < 1% 应触发 bearish shareholder_return_signal."""
    metrics = _make_financial_metrics()
    metrics["dividend_yield"] = 0.005  # 0.5% < 1%
    state = {
        "messages": [],
        "data": {
            "ticker": "000858",
            "end_date": "2026-07-18",
            "portfolio": {"cash": 100000.0, "stock": 0},
            "financial_metrics": [metrics],
        },
        "metadata": {"show_reasoning": False, "model": "openai"},
    }
    result = fundamentals_agent(state)
    content = json.loads(result["messages"][0].content)

    sig = content["reasoning"]["shareholder_return_signal"]
    assert sig["signal"] == "bearish"


def test_fundamentals_dividend_signal_flags_high_payout():
    """股息率 bullish 但支付率 > 80% 应附加可持续性提示."""
    metrics = _make_financial_metrics()
    metrics["dividend_yield"] = 0.05  # 5% > 4%, bullish
    metrics["payout_ratio"] = 1.5  # 150% > 80%, 不可持续
    state = {
        "messages": [],
        "data": {
            "ticker": "000858",
            "end_date": "2026-07-18",
            "portfolio": {"cash": 100000.0, "stock": 0},
            "financial_metrics": [metrics],
        },
        "metadata": {"show_reasoning": False, "model": "openai"},
    }
    result = fundamentals_agent(state)
    content = json.loads(result["messages"][0].content)

    sig = content["reasoning"]["shareholder_return_signal"]
    assert sig["signal"] == "bullish"
    assert "可持续性" in sig["details"]


# ---------------------------------------------------------------------------
# valuation_agent evidence
# ---------------------------------------------------------------------------


def test_valuation_output_includes_evidence():
    state = {
        "messages": [],
        "data": {
            "ticker": "600519",
            "end_date": "2026-07-18",
            "portfolio": {"cash": 100000.0, "stock": 0},
            "financial_metrics": [_make_financial_metrics()],
            "financial_line_items": _make_financial_line_items(),
            "market_cap": 50_000_000_000,
        },
        "metadata": {"show_reasoning": False, "model": "openai"},
    }
    result = valuation_agent(state)
    content = json.loads(result["messages"][0].content)

    assert "evidence" in content
    assert isinstance(content["evidence"], dict)
    ev = content["evidence"]
    assert "dcf_value" in ev
    assert "owner_earnings_value" in ev
    assert ev["market_cap"] == 50_000_000_000
    assert "dcf_gap" in ev
    assert "owner_earnings_gap" in ev
    assert "valuation_gap" in ev


def test_valuation_evidence_handles_zero_market_cap():
    """When market_cap is 0, gaps should be 0 but evidence still present."""
    state = {
        "messages": [],
        "data": {
            "ticker": "600519",
            "end_date": "2026-07-18",
            "portfolio": {"cash": 100000.0, "stock": 0},
            "financial_metrics": [_make_financial_metrics()],
            "financial_line_items": _make_financial_line_items(),
            "market_cap": 0,
        },
        "metadata": {"show_reasoning": False, "model": "openai"},
    }
    result = valuation_agent(state)
    content = json.loads(result["messages"][0].content)

    ev = content["evidence"]
    assert ev["market_cap"] == 0.0
    assert ev["dcf_gap"] == 0.0
    assert ev["valuation_gap"] == 0.0


# ---------------------------------------------------------------------------
# technicals_agent evidence
# ---------------------------------------------------------------------------


def test_technicals_output_includes_evidence():
    state = {
        "messages": [],
        "data": {
            "ticker": "600519",
            "end_date": "2026-07-18",
            "portfolio": {"cash": 100000.0, "stock": 0},
            "prices": _make_prices_records(120),
        },
        "metadata": {"show_reasoning": False, "model": "openai"},
    }
    result = technical_analyst_agent(state)
    content = json.loads(result["messages"][0].content)

    assert "evidence" in content
    assert isinstance(content["evidence"], dict)
    ev = content["evidence"]
    # All evidence fields should be floats
    for key in ("adx", "rsi_14", "momentum_1m", "momentum_3m",
                "momentum_6m", "historical_volatility",
                "hurst_exponent", "skewness"):
        assert key in ev, f"evidence missing {key}"
        assert isinstance(ev[key], (int, float))


# ---------------------------------------------------------------------------
# risk_manager_agent evidence
# ---------------------------------------------------------------------------


def test_risk_manager_output_includes_evidence():
    state = {
        "messages": [
            {"name": "bull_bear_debate_agent", "content": json.dumps({
                "signal": "bullish",
                "confidence": 0.7,
                "bull_confidence": 0.8,
                "bear_confidence": 0.3,
            })},
        ],
        "data": {
            "ticker": "600519",
            "end_date": "2026-07-18",
            "portfolio": {"cash": 100000.0, "stock": 0},
            "prices": _make_prices_records(120),
        },
        "metadata": {"show_reasoning": False, "model": "openai"},
    }
    # risk_manager expects LangChain HumanMessage, but accepts dict-like with .name/.content
    # Use a simple stub
    from langchain_core.messages import HumanMessage
    state["messages"] = [HumanMessage(
        content=json.dumps({
            "signal": "bullish",
            "confidence": 0.7,
            "bull_confidence": 0.8,
            "bear_confidence": 0.3,
        }),
        name="bull_bear_debate_agent",
    )]

    result = risk_management_agent(state)
    content = json.loads(result["messages"][-1].content)

    assert "evidence" in content
    assert isinstance(content["evidence"], dict)
    ev = content["evidence"]
    assert "volatility" in ev
    assert "value_at_risk_95" in ev
    assert "max_drawdown" in ev
    assert "market_risk_score" in ev
    assert "risk_score" in ev
    assert isinstance(ev["volatility"], (int, float))
    assert isinstance(ev["risk_score"], int)
