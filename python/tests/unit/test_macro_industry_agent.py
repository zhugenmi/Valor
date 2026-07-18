"""Unit tests for macro_industry_agent.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

import json

from valor.agents.macro_industry import macro_industry_agent


def _make_state(ticker: str = "600519") -> dict:
    return {
        "messages": [],
        "data": {
            "ticker": ticker,
            "end_date": "2026-07-18",
            "portfolio": {"cash": 100000.0, "stock": 0},
        },
        "metadata": {"show_reasoning": False, "model": "openai"},
    }


def test_macro_industry_agent_returns_correct_message_name(monkeypatch):
    """Agent must append a HumanMessage with name='macro_industry_agent'."""
    monkeypatch.setattr(
        "valor.agents.macro_industry.get_stock_news",
        lambda *a, **kw: [{"title": "test", "content": "test", "publish_time": "2026-07-15 10:00:00"}],
    )
    fake_llm_response = json.dumps({
        "macro_environment": "bullish",
        "industry_outlook": "neutral",
        "policy_impact": "positive",
        "key_factors": ["降准0.5个百分点"],
        "risk_flags": [],
        "reasoning": "央行降准利好市场流动性，行业政策稳定",
    })
    monkeypatch.setattr(
        "valor.agents.macro_industry.get_chat_completion",
        lambda messages: fake_llm_response,
    )

    result = macro_industry_agent(_make_state())

    assert len(result["messages"]) == 1
    assert result["messages"][0].name == "macro_industry_agent"


def test_macro_industry_agent_output_schema(monkeypatch):
    """Output JSON must contain all 6 required fields."""
    monkeypatch.setattr(
        "valor.agents.macro_industry.get_stock_news",
        lambda *a, **kw: [{"title": "t", "content": "c", "publish_time": "2026-07-15 10:00:00"}],
    )
    fake_llm_response = json.dumps({
        "macro_environment": "bullish",
        "industry_outlook": "bullish",
        "policy_impact": "positive",
        "key_factors": ["factor1"],
        "risk_flags": ["监管问询"],
        "reasoning": "test reasoning",
    })
    monkeypatch.setattr(
        "valor.agents.macro_industry.get_chat_completion",
        lambda messages: fake_llm_response,
    )

    result = macro_industry_agent(_make_state())
    content = json.loads(result["messages"][0].content)

    required_fields = {
        "macro_environment", "industry_outlook", "policy_impact",
        "key_factors", "risk_flags", "reasoning",
    }
    assert required_fields.issubset(content.keys())
    assert content["macro_environment"] in {"bullish", "neutral", "bearish"}
    assert isinstance(content["key_factors"], list)
    assert isinstance(content["risk_flags"], list)


def test_macro_industry_agent_fetches_both_stock_and_market_news(monkeypatch):
    """Agent must call get_stock_news twice: once for ticker, once for 沪深300指数."""
    calls: list[str] = []

    def fake_get_stock_news(symbol, *a, **kw):
        calls.append(symbol)
        return [{"title": "t", "content": "c", "publish_time": "2026-07-15 10:00:00"}]

    monkeypatch.setattr("valor.agents.macro_industry.get_stock_news", fake_get_stock_news)
    monkeypatch.setattr(
        "valor.agents.macro_industry.get_chat_completion",
        lambda messages: '{"macro_environment":"neutral","industry_outlook":"neutral","policy_impact":"neutral","key_factors":[],"risk_flags":[],"reasoning":"test"}',
    )

    macro_industry_agent(_make_state(ticker="600519"))

    assert "600519" in calls
    assert "沪深300指数" in calls


def test_macro_industry_agent_writes_data_field(monkeypatch):
    """Agent must write state['data']['macro_industry_analysis'] with the parsed result."""
    monkeypatch.setattr(
        "valor.agents.macro_industry.get_stock_news",
        lambda *a, **kw: [{"title": "t", "content": "c", "publish_time": "2026-07-15 10:00:00"}],
    )
    monkeypatch.setattr(
        "valor.agents.macro_industry.get_chat_completion",
        lambda messages: '{"macro_environment":"neutral","industry_outlook":"neutral","policy_impact":"neutral","key_factors":[],"risk_flags":[],"reasoning":"test"}',
    )

    state = _make_state()
    result = macro_industry_agent(state)

    assert "macro_industry_analysis" in result["data"]
    assert result["data"]["macro_industry_analysis"]["macro_environment"] == "neutral"
