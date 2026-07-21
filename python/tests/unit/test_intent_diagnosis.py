"""Test intent classifier recognizes 诊断 keyword. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from valor.server.intent import classify_intent


async def _mock_chat(**_kwargs):
    return '{"intent": "full_analysis", "ticker": "600519", "agent": null, "reply": null}'


async def test_diagnosis_keyword_triggers_full_analysis():
    with patch("valor.server.intent.get_llm_provider") as mock_provider:
        mock_provider.return_value.chat = AsyncMock(side_effect=_mock_chat)
        result = await classify_intent("诊断股票600519")
    assert result.intent == "full_analysis"
    assert result.ticker == "600519"
    assert result.agent is None


async def test_diagnosis_fallback_regex():
    """When LLM unavailable, regex fallback should still extract ticker."""
    with patch("valor.server.intent.get_llm_provider", side_effect=RuntimeError("no provider")):
        result = await classify_intent("诊断股票600519")
    assert result.intent == "full_analysis"
    assert result.ticker == "600519"


def test_intent_result_agents_field_and_agent_property():
    """IntentResult 支持 agents 列表，agent property 返回首个。"""
    from valor.server.intent import IntentResult

    # 多 agent
    r = IntentResult(intent="single_analysis", ticker="600519",
                     agents=["technicals", "valuation"])
    assert r.agents == ["technicals", "valuation"]
    assert r.agent == "technicals"

    # 单 agent
    r2 = IntentResult(intent="single_analysis", ticker="600519", agents=["valuation"])
    assert r2.agents == ["valuation"]
    assert r2.agent == "valuation"

    # 空 agents
    r3 = IntentResult(intent="full_analysis", ticker="600519", agents=[])
    assert r3.agents == []
    assert r3.agent is None


def test_coerce_multi_agent_from_llm():
    """_coerce 应从 LLM 的 agents 数组构造 IntentResult。"""
    from valor.server.intent import _coerce

    raw = {
        "intent": "single_analysis",
        "ticker": "600519",
        "agents": ["technicals", "valuation"],
        "reply": None,
    }
    result = _coerce(raw)
    assert result.intent == "single_analysis"
    assert result.agents == ["technicals", "valuation"]
    assert result.agent == "technicals"


def test_coerce_filters_invalid_agent_keys():
    """_coerce 应过滤掉无效 agent key，过滤后为空则回退 full_analysis。"""
    from valor.server.intent import _coerce

    raw = {
        "intent": "single_analysis",
        "ticker": "600519",
        "agents": ["technicals", "invalid_key"],
        "reply": None,
    }
    result = _coerce(raw)
    assert result.agents == ["technicals"]
    assert result.intent == "single_analysis"

    # 全部无效 -> 回退 full_analysis
    raw2 = {
        "intent": "single_analysis",
        "ticker": "600519",
        "agents": ["invalid1", "invalid2"],
        "reply": None,
    }
    result2 = _coerce(raw2)
    assert result2.agents == []
    assert result2.intent == "full_analysis"


async def _mock_multi_agent_chat(**_kwargs):
    return ('{"intent": "single_analysis", "ticker": "600519", '
            '"agents": ["technicals", "valuation"], "reply": null}')


async def test_classify_intent_multi_agent():
    """LLM 返回多 agent 时，classify_intent 应正确解析。"""
    with patch("valor.server.intent.get_llm_provider") as mock_provider:
        mock_provider.return_value.chat = AsyncMock(side_effect=_mock_multi_agent_chat)
        result = await classify_intent("五粮液技术面和估值")
    assert result.intent == "single_analysis"
    assert result.ticker == "600519"
    assert result.agents == ["technicals", "valuation"]


async def test_fallback_regex_with_dimension_keywords():
    """LLM 不可用时，正则降级应识别维度关键词。"""
    with patch("valor.server.intent.get_llm_provider", side_effect=RuntimeError("no provider")):
        result = await classify_intent("600519 估值 技术面")
    assert result.intent == "single_analysis"
    assert result.ticker == "600519"
    assert set(result.agents) == {"valuation", "technicals"}


async def test_fallback_regex_no_dimension_returns_full_analysis():
    """LLM 不可用且无维度关键词时，回退 full_analysis。"""
    with patch("valor.server.intent.get_llm_provider", side_effect=RuntimeError("no provider")):
        result = await classify_intent("分析五粮液 000858")
    assert result.intent == "full_analysis"
    assert result.ticker == "000858"
    assert result.agents == []