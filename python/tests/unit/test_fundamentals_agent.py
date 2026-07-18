"""Unit tests for fundamentals_agent risk_flags field.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

import json

from valor.agents.fundamentals import fundamentals_agent


def _make_state() -> dict:
    return {
        "messages": [],
        "data": {
            "ticker": "600519",
            "end_date": "2026-07-18",
            "portfolio": {"cash": 100000.0, "stock": 0},
            "financial_metrics": [{
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
            }],
        },
        "metadata": {"show_reasoning": False, "model": "openai"},
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
