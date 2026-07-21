"""Unit tests for _polish_node_output in stream.py.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

import json
from unittest.mock import AsyncMock, patch

from langchain_core.messages import HumanMessage

from valor.server.routes.stream import _polish_node_output


def _msg(name: str, content: dict | str) -> HumanMessage:
    if isinstance(content, dict):
        content = json.dumps(content, ensure_ascii=False)
    return HumanMessage(content=content, name=name)


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
