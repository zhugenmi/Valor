"""Unit tests for polish_decision prompt construction and _polish_node_output.

Verifies that valuation agent gets field hints injected into the user message,
that the strengthened system prompt forbids fabricating numbers, and that the
stream node polishing relays the last matching agent message.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

import json
from unittest.mock import AsyncMock, patch

from langchain_core.messages import HumanMessage

from valor.server.polish import polish_decision
from valor.server.routes.stream import _polish_node_output


def _capture_messages():
    """Return a mock provider whose .chat records the messages it was called with."""
    captured: dict = {}

    async def _chat(messages, **kwargs):
        captured["messages"] = messages
        return "## 估值分析\n整体中性"

    provider = AsyncMock()
    provider.chat.side_effect = _chat
    return provider, captured


def _msg(name: str, content: dict | str) -> HumanMessage:
    if isinstance(content, dict):
        content = json.dumps(content, ensure_ascii=False)
    return HumanMessage(content=content, name=name)


async def test_valuation_gets_field_hints_in_user_message():
    """valuation agent 的 user_content 必须包含 gap 字段含义说明。"""
    provider, captured = _capture_messages()
    with patch("valor.server.polish.get_llm_provider", return_value=provider):
        await polish_decision("601728", "valuation", {
            "signal": "neutral",
            "confidence": "3%",
            "reasoning": {
                "dcf_analysis": {"signal": "bullish", "details": "..."},
                "owner_earnings_analysis": {"signal": "bearish", "details": "..."},
            },
            "evidence": {
                "dcf_gap": 0.493,
                "owner_earnings_gap": -0.44,
                "valuation_gap": 0.026,
            },
        })
    user_msg = captured["messages"][1].content
    # 字段说明中的关键词必须出现
    assert "evidence.dcf_gap" in user_msg
    assert "正值=内在价值高于市值=低估=看涨" in user_msg
    assert "负值=内在价值低于市值=高估=看跌" in user_msg
    assert "严禁强行声称" in user_msg  # 子信号不一致约束


async def test_non_valuation_agents_get_no_field_hints():
    """technicals 等 agent 的 user_content 不应包含 valuation 专属字段说明。"""
    provider, captured = _capture_messages()
    with patch("valor.server.polish.get_llm_provider", return_value=provider):
        await polish_decision("601728", "technicals", {
            "signal": "bullish",
            "confidence": "60%",
            "reasoning": {"trend_following": {"signal": "bullish"}},
        })
    user_msg = captured["messages"][1].content
    assert "evidence.dcf_gap" not in user_msg
    assert "估值分析字段含义" not in user_msg


async def test_system_prompt_forbids_fabricating_numbers():
    """强化后的 system prompt 必须包含严禁编造数字和方向以 signal 为准的约束。"""
    provider, captured = _capture_messages()
    with patch("valor.server.polish.get_llm_provider", return_value=provider):
        await polish_decision("601728", "technicals", {"signal": "bullish"})
    system_msg = captured["messages"][0].content
    assert "严禁自行计算、估算或编造" in system_msg
    assert "signal 字段为准" in system_msg
    assert "严禁声称" in system_msg  # 子信号不一致约束


async def test_valuation_decision_json_included_in_user_message():
    """原始 decision JSON 必须完整出现在 user_content 中，供 LLM 引用。"""
    provider, captured = _capture_messages()
    decision = {
        "signal": "neutral",
        "evidence": {"dcf_gap": 0.493, "owner_earnings_gap": -0.44},
    }
    with patch("valor.server.polish.get_llm_provider", return_value=provider):
        await polish_decision("601728", "valuation", decision)
    user_msg = captured["messages"][1].content
    assert "0.493" in user_msg
    assert "-0.44" in user_msg


async def test_polish_node_output_extracts_and_polishes():
    """technicals 节点的最后一条消息应被 polish_decision 处理。"""
    state_delta = {
        "messages": [
            _msg("technical_analyst_agent", {"signal": "bullish", "confidence": 0.6}),
        ],
    }
    with patch(
        "valor.server.routes.stream.polish_decision",
        new=AsyncMock(return_value="## 技术面分析\n整体偏多"),
    ) as mock_polish:
        result = await _polish_node_output("601728", "technicals", state_delta)
    assert result == "## 技术面分析\n整体偏多"
    mock_polish.assert_awaited_once()
    # 第二个位置参数是 node_name
    args = mock_polish.call_args.args
    assert args[0] == "601728"
    assert args[1] == "technicals"
    assert args[2] == {"signal": "bullish", "confidence": 0.6}


async def test_polish_node_output_market_data_returns_none():
    """market_data 不在 _NODE_TO_MSG_NAME 中 -> 返回 None，不调用 polish。"""
    with patch(
        "valor.server.routes.stream.polish_decision",
        new=AsyncMock(),
    ) as mock_polish:
        result = await _polish_node_output("601728", "market_data", {"messages": []})
    assert result is None
    mock_polish.assert_not_awaited()


async def test_polish_node_output_no_matching_message_returns_none():
    """messages 中没有目标 name 的消息 -> 返回 None。"""
    state_delta = {
        "messages": [
            _msg("fundamentals_agent", {"signal": "bullish"}),
        ],
    }
    with patch(
        "valor.server.routes.stream.polish_decision",
        new=AsyncMock(),
    ) as mock_polish:
        result = await _polish_node_output("601728", "technicals", state_delta)
    assert result is None
    mock_polish.assert_not_awaited()


async def test_polish_node_output_uses_last_matching_message():
    """多条同名消息时，取最后一条。"""
    state_delta = {
        "messages": [
            _msg("technical_analyst_agent", {"signal": "neutral", "confidence": 0.3}),
            _msg("technical_analyst_agent", {"signal": "bullish", "confidence": 0.7}),
        ],
    }
    with patch(
        "valor.server.routes.stream.polish_decision",
        new=AsyncMock(return_value="markdown"),
    ) as mock_polish:
        await _polish_node_output("601728", "technicals", state_delta)
    args = mock_polish.call_args.args
    assert args[2] == {"signal": "bullish", "confidence": 0.7}


async def test_polish_node_output_invalid_json_falls_back_to_raw():
    """msg.content 不是合法 JSON -> 用 {"raw": str(content)} 调用 polish。"""
    state_delta = {
        "messages": [_msg("technical_analyst_agent", "not json content")],
    }
    with patch(
        "valor.server.routes.stream.polish_decision",
        new=AsyncMock(return_value="markdown"),
    ) as mock_polish:
        await _polish_node_output("601728", "technicals", state_delta)
    args = mock_polish.call_args.args
    assert args[2] == {"raw": "not json content"}