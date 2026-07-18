"""Unit tests for bull_bear_debate_agent.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

import json

from langchain_core.messages import HumanMessage

from valor.agents.bull_bear_debate import bull_bear_debate_agent


def _dimension_msg(name: str, signal: str = "neutral") -> HumanMessage:
    return HumanMessage(
        content=json.dumps({"signal": signal, "confidence": "50%", "reasoning": "test"}),
        name=name,
    )


def _make_state() -> dict:
    return {
        "messages": [
            _dimension_msg("technical_analyst_agent", "bullish"),
            _dimension_msg("fundamentals_agent", "bullish"),
            _dimension_msg("valuation_agent", "neutral"),
            _dimension_msg("capital_sentiment_agent", "bearish"),
            _dimension_msg("macro_industry_agent", "neutral"),
        ],
        "data": {"ticker": "600519", "portfolio": {"cash": 100000.0, "stock": 0}},
        "metadata": {"show_reasoning": False, "model": "openai"},
    }


def _fake_llm_factory():
    """Returns a fake LLM that returns different responses based on prompt content."""
    def fake(messages):
        content = messages[-1]["content"] if isinstance(messages[-1], dict) else messages[-1].content
        if "多方研究员" in content:
            return json.dumps({
                "signal": "bullish",
                "confidence": 0.7,
                "key_points": ["[基本面] ROE高"],
                "reasoning": "多方论点",
            })
        if "空方研究员" in content:
            return json.dumps({
                "signal": "bearish",
                "confidence": 0.4,
                "key_points": ["[估值] PE偏高"],
                "reasoning": "空方论点",
            })
        if "辩论室裁决者" in content:
            return json.dumps({
                "signal": "bullish",
                "confidence": 0.65,
                "bull_confidence": 0.7,
                "bear_confidence": 0.4,
                "reasoning": "多方占优",
            })
        return "{}"
    return fake


def test_bull_bear_debate_appends_three_messages(monkeypatch):
    """Agent must append 3 sub-messages: bull_case, bear_case, verdict."""
    monkeypatch.setattr(
        "valor.agents.bull_bear_debate.get_chat_completion",
        _fake_llm_factory(),
    )

    result = bull_bear_debate_agent(_make_state())

    # 5 input + 3 new = 8
    assert len(result["messages"]) == 8
    names = [m.name for m in result["messages"][-3:]]
    assert names == ["bull_case_agent", "bear_case_agent", "bull_bear_debate_agent"]


def test_bull_bear_debate_verdict_schema(monkeypatch):
    monkeypatch.setattr(
        "valor.agents.bull_bear_debate.get_chat_completion",
        _fake_llm_factory(),
    )

    result = bull_bear_debate_agent(_make_state())

    verdict = json.loads(result["messages"][-1].content)
    required = {"signal", "confidence", "bull_confidence", "bear_confidence", "reasoning"}
    assert required.issubset(verdict.keys())
    assert verdict["signal"] in {"bullish", "neutral", "bearish"}


def test_bull_bear_debate_writes_data_field(monkeypatch):
    monkeypatch.setattr(
        "valor.agents.bull_bear_debate.get_chat_completion",
        _fake_llm_factory(),
    )

    result = bull_bear_debate_agent(_make_state())

    assert "debate_analysis" in result["data"]
    assert result["data"]["debate_analysis"]["signal"] == "bullish"


def test_bull_bear_debate_calls_llm_three_times(monkeypatch):
    """Agent must call LLM exactly 3 times: bull, bear, verdict."""
    call_count = [0]

    def fake(messages):
        call_count[0] += 1
        return _fake_llm_factory()(messages)

    monkeypatch.setattr("valor.agents.bull_bear_debate.get_chat_completion", fake)

    bull_bear_debate_agent(_make_state())

    assert call_count[0] == 3


def test_bull_bear_debate_missing_dimension_uses_neutral(monkeypatch):
    """If a dimension message is missing, agent must fall back to neutral, not crash."""
    monkeypatch.setattr(
        "valor.agents.bull_bear_debate.get_chat_completion",
        _fake_llm_factory(),
    )

    state = _make_state()
    # Remove one dimension message
    state["messages"] = [m for m in state["messages"] if m.name != "macro_industry_agent"]

    result = bull_bear_debate_agent(state)
    assert len(result["messages"]) == 7  # 4 input + 3 new
