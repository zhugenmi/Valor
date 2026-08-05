"""Integration test: /agents/stream with VALOR_USE_AGENT_RUNTIME=1.
License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from valor.server.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _parse_events(text: str) -> list[dict]:
    events = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block.startswith("data: "):
            continue
        events.append(json.loads(block[len("data: "):]))
    return events


def test_runtime_path_emits_tool_events_and_message(client, monkeypatch):
    """VALOR_USE_AGENT_RUNTIME=1 -> stream.py calls run_agent_runtime."""
    monkeypatch.setenv("VALOR_USE_AGENT_RUNTIME", "1")

    async def _fake_runtime(query, **kwargs):
        yield {"event": "reasoning_started", "data": {}}
        yield {
            "event": "tool_call",
            "data": {"id": "c1", "name": "kb_search", "arguments": {"query": "茅台"}},
        }
        yield {
            "event": "tool_result",
            "data": {"id": "c1", "name": "kb_search", "result": {"chunks": []}, "error": None},
        }
        yield {
            "event": "message",
            "data": {"role": "agent", "payload": {"content": "基于知识库...茅台..."}},
        }
        yield {"event": "reasoning_completed", "data": {}}
        yield {"event": "done", "data": {}}

    with (
        patch("valor.server.routes.stream.run_agent_runtime", _fake_runtime),
        patch("valor.server.routes.stream.create_conversation"),
        patch("valor.server.routes.stream.append_message"),
        patch("valor.server.routes.stream.update_conversation_status"),
    ):
        resp = client.post(
            "/api/v1/agents/stream",
            json={"query": "茅台有什么研究报告", "agent_name": "ValorAgent"},
        )

    events = _parse_events(resp.text)
    types = [e["event"] for e in events]
    assert types[0] == "conversation_started"
    assert "tool_call" in types
    assert "tool_result" in types
    assert "message" in types
    assert types[-1] == "done"


def test_runtime_disabled_by_default_uses_old_path(client, monkeypatch):
    """Without env var, old classify_intent path is used (regression check)."""
    monkeypatch.delenv("VALOR_USE_AGENT_RUNTIME", raising=False)

    from valor.server.intent import IntentResult

    async def _chat_intent(_q):
        return IntentResult(intent="chat", reply="您好！")

    with (
        patch("valor.server.routes.stream.classify_intent", _chat_intent),
        patch("valor.server.routes.stream.kb_search", return_value=[]),
        patch("valor.server.routes.stream.create_conversation"),
        patch("valor.server.routes.stream.append_message"),
        patch("valor.server.routes.stream.update_conversation_status"),
        patch("valor.server.routes.stream.run_agent_runtime") as mock_runtime,
    ):
        resp = client.post(
            "/api/v1/agents/stream",
            json={"query": "你好", "agent_name": "ValorAgent"},
        )
        resp.text

    mock_runtime.assert_not_called()