"""Test Supervisor loop with mocked ToolCallingProvider.
License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial"""
from __future__ import annotations

from unittest.mock import patch

from valor.adapters.llm.protocol import (
    ToolCall,
    ToolCallResponse,
)
from valor.runtime.supervisor import run_supervisor
from valor.runtime.tools import get_default_tools


class _FakeProvider:
    """Fake ToolCallingProvider with scripted responses."""

    def __init__(self, responses: list[ToolCallResponse]):
        self._responses = list(responses)
        self.calls = 0

    async def chat_with_tools(self, messages, tools, **kwargs):
        resp = self._responses[self.calls]
        self.calls += 1
        return resp


async def test_supervisor_no_tool_calls_returns_immediately():
    """LLM returns content with no tool_calls -> Supervisor exits after 1 iter."""
    provider = _FakeProvider([
        ToolCallResponse(content="你好！请提供股票代码。", tool_calls=None, finish_reason="stop"),
    ])
    events: list[dict] = []

    async def _on_event(evt):
        events.append(evt)

    state = await run_supervisor(
        query="你好",
        tools=get_default_tools(),
        provider=provider,  # type: ignore[arg-type]
        on_event=_on_event,
    )
    assert state.finished is True
    assert state.iterations == 1
    assert state.final_answer is None  # answer generation is separate


async def test_supervisor_executes_tool_call_then_stops():
    """LLM asks for kb_search, then on next iter returns content (no tools)."""
    provider = _FakeProvider([
        ToolCallResponse(
            content=None,
            tool_calls=[ToolCall(id="c1", name="kb_search", arguments={"query": "茅台"})],
            finish_reason="tool_calls",
        ),
        ToolCallResponse(content="Based on KB...", tool_calls=None, finish_reason="stop"),
    ])
    events: list[dict] = []

    async def _on_event(evt):
        events.append(evt)

    fake_chunks = [{"chunk_id": "c1", "doc_title": "茅台研究", "text": "..."}]
    with patch("valor.runtime.tools.kb_search_search", return_value=fake_chunks):
        state = await run_supervisor(
            query="茅台有什么研究报告",
            tools=get_default_tools(),
            provider=provider,  # type: ignore[arg-type]
            on_event=_on_event,
        )

    assert state.iterations == 2
    assert len(state.tool_results) == 1
    assert state.tool_results[0].name == "kb_search"
    assert state.tool_results[0].result["chunks"] == fake_chunks

    # Events: tool_call + tool_result emitted
    event_types = [e["event"] for e in events]
    assert "tool_call" in event_types
    assert "tool_result" in event_types


async def test_supervisor_invalid_tool_name_returns_error_to_llm():
    """LLM asks for nonexistent tool -> error result is appended to messages."""
    provider = _FakeProvider([
        ToolCallResponse(
            content=None,
            tool_calls=[ToolCall(id="c1", name="nonexistent_tool", arguments={})],
            finish_reason="tool_calls",
        ),
        ToolCallResponse(content="Sorry, I cannot help with that.", tool_calls=None, finish_reason="stop"),
    ])
    events: list[dict] = []

    async def _on_event(evt):
        events.append(evt)

    state = await run_supervisor(
        query="test",
        tools=get_default_tools(),
        provider=provider,  # type: ignore[arg-type]
        on_event=_on_event,
    )

    # The tool_result message should contain an error
    tool_msgs = [m for m in state.messages if m.role == "tool"]
    assert len(tool_msgs) == 1
    assert "error" in (tool_msgs[0].content or "")


async def test_supervisor_max_iterations_stops_loop():
    """If LLM keeps requesting tools, Supervisor stops at max_iterations."""
    # Always returns a tool_call -> infinite loop without guard
    always_tool = ToolCallResponse(
        content=None,
        tool_calls=[ToolCall(id="c1", name="kb_search", arguments={"query": "x"})],
        finish_reason="tool_calls",
    )
    provider = _FakeProvider([always_tool] * 20)
    events: list[dict] = []

    async def _on_event(evt):
        events.append(evt)

    with patch("valor.runtime.tools.kb_search_search", return_value=[]):
        state = await run_supervisor(
            query="loop test",
            tools=get_default_tools(),
            provider=provider,  # type: ignore[arg-type]
            on_event=_on_event,
            max_iterations=3,
        )

    assert state.iterations == 3
    assert state.finished is True
    # Should emit a max_iterations_reached event
    event_types = [e["event"] for e in events]
    assert "max_iterations_reached" in event_types


async def test_supervisor_tool_handler_failure_isolated():
    """If a tool handler raises, Supervisor catches and returns error to LLM."""
    provider = _FakeProvider([
        ToolCallResponse(
            content=None,
            tool_calls=[ToolCall(id="c1", name="kb_search", arguments={"query": "x"})],
            finish_reason="tool_calls",
        ),
        ToolCallResponse(content="OK", tool_calls=None, finish_reason="stop"),
    ])
    events: list[dict] = []

    async def _on_event(evt):
        events.append(evt)

    # Make kb_search_search raise
    with patch("valor.runtime.tools.kb_search_search", side_effect=RuntimeError("boom")):
        state = await run_supervisor(
            query="test",
            tools=get_default_tools(),
            provider=provider,  # type: ignore[arg-type]
            on_event=_on_event,
        )

    tool_msgs = [m for m in state.messages if m.role == "tool"]
    assert len(tool_msgs) == 1
    assert "boom" in (tool_msgs[0].content or "")


async def test_run_agent_runtime_yields_events_without_deadlock():
    """run_agent_runtime must terminate (no deadlock) and yield expected events.

    Patches get_llm_provider to return a _FakeProvider that returns no tool_calls
    on first call (Supervisor exits after 1 iter). Verifies the queue sentinel
    fix: if None is never put, this test hangs forever.
    """
    from valor.runtime.main import run_agent_runtime

    fake_provider = _FakeProvider([
        ToolCallResponse(content="done", tool_calls=None, finish_reason="stop"),
    ])

    async def _fake_answer(supervisor_messages, user_query, provider=None):
        return "mocked final answer"

    with (
        patch("valor.runtime.main.get_llm_provider", return_value=fake_provider),
        patch("valor.runtime.main.generate_answer", side_effect=_fake_answer),
    ):
        events = []
        async for evt in run_agent_runtime("hello"):
            events.append(evt)

    event_types = [e["event"] for e in events]
    # Must include reasoning_started, message, reasoning_completed, done
    assert "reasoning_started" in event_types
    assert "message" in event_types
    assert "reasoning_completed" in event_types
    assert "done" in event_types
    # The message event must contain the final answer
    msg_evt = next(e for e in events if e["event"] == "message")
    assert msg_evt["data"]["payload"]["content"] == "mocked final answer"


async def test_supervisor_injects_kb_catalog_into_system_message():
    """KB document catalog is fetched at Supervisor start and appended to the
    system prompt, so the LLM sees all documents without calling a tool."""
    from valor.knowledge_base.models import KBDoc

    fake_docs = [
        KBDoc(
            doc_id="d1",
            title="茅台2025年报",
            category="disclosure",
            sub_type="annual_report",
            mime_type="application/pdf",
            file_path="/tmp/d1.pdf",
            sha256="abc",
            uploaded_at="2026-04-16T10:00:00",
            publish_date="2026-04-16",
            ticker="600519",
            chunk_count=748,
            status="ready",
        ),
    ]
    provider = _FakeProvider([
        ToolCallResponse(content="OK", tool_calls=None, finish_reason="stop"),
    ])

    async def _on_event(evt):
        pass

    with patch(
        "valor.runtime.supervisor.kb_list_documents",
        return_value=(fake_docs, 1),
    ):
        state = await run_supervisor(
            query="知识库有哪些文档",
            tools=get_default_tools(),
            provider=provider,  # type: ignore[arg-type]
            on_event=_on_event,
        )

    # First message is the system prompt; catalog must be appended
    sys_msg = state.messages[0]
    assert sys_msg.role == "system"
    assert "当前知识库文档目录" in sys_msg.content
    assert "茅台2025年报" in sys_msg.content
    assert "600519" in sys_msg.content
    assert "748 chunks" in sys_msg.content


async def test_supervisor_works_when_kb_catalog_fetch_fails():
    """If kb_list_documents raises, Supervisor still runs (catalog omitted)."""
    provider = _FakeProvider([
        ToolCallResponse(content="OK", tool_calls=None, finish_reason="stop"),
    ])

    async def _on_event(evt):
        pass

    with patch(
        "valor.runtime.supervisor.kb_list_documents",
        side_effect=RuntimeError("db down"),
    ):
        state = await run_supervisor(
            query="你好",
            tools=get_default_tools(),
            provider=provider,  # type: ignore[arg-type]
            on_event=_on_event,
        )

    sys_msg = state.messages[0]
    # Catalog header (## prefix) only appears when fetch succeeded
    assert "## 当前知识库文档目录" not in sys_msg.content
    assert state.finished is True