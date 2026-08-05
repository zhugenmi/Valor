"""Test runtime types: ToolCall/ToolCallResponse/RuntimeMessage serialization.
License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial"""
from __future__ import annotations

import pytest

from valor.adapters.llm.protocol import (
    RuntimeMessage,
    ToolCall,
    ToolCallResponse,
    ToolSchema,
)


def test_tool_call_parses_arguments_dict():
    tc = ToolCall(id="call_1", name="kb_search", arguments={"query": "茅台"})
    assert tc.id == "call_1"
    assert tc.arguments == {"query": "茅台"}


def test_tool_call_response_with_tool_calls():
    resp = ToolCallResponse(
        content="Let me search the knowledge base.",
        tool_calls=[ToolCall(id="call_1", name="kb_search", arguments={"query": "茅台"})],
        finish_reason="tool_calls",
    )
    assert resp.tool_calls is not None
    assert resp.tool_calls[0].name == "kb_search"


def test_tool_call_response_without_tool_calls():
    resp = ToolCallResponse(content="Final answer", tool_calls=None, finish_reason="stop")
    assert resp.tool_calls is None
    assert resp.content == "Final answer"


def test_runtime_message_user():
    msg = RuntimeMessage(role="user", content="分析600519")
    assert msg.role == "user"
    assert msg.content == "分析600519"
    assert msg.tool_calls is None


def test_runtime_message_assistant_with_tool_calls():
    msg = RuntimeMessage(
        role="assistant",
        content=None,
        tool_calls=[ToolCall(id="call_1", name="kb_search", arguments={"query": "茅台"})],
    )
    assert msg.role == "assistant"
    assert msg.tool_calls is not None


def test_runtime_message_tool_result():
    msg = RuntimeMessage(
        role="tool",
        content='{"chunks": []}',
        tool_call_id="call_1",
        name="kb_search",
    )
    assert msg.role == "tool"
    assert msg.tool_call_id == "call_1"


def test_tool_schema_to_openai_format():
    schema = ToolSchema(
        name="kb_search",
        description="Search the knowledge base",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )
    openai_schema = schema.to_openai_format()
    assert openai_schema["type"] == "function"
    assert openai_schema["function"]["name"] == "kb_search"
    assert openai_schema["function"]["parameters"]["properties"]["query"]["type"] == "string"


def test_runtime_message_invalid_role_rejected():
    with pytest.raises(Exception):
        RuntimeMessage(role="invalid_role", content="test")