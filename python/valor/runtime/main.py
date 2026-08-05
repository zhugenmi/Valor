"""Agent Runtime main entry: run_agent_runtime(query) -> AsyncIterator[SSE event].

Wires Supervisor + Answer generator together. Yields SSE-compatible event
dicts that stream.py forwards to the client.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
from __future__ import annotations

from typing import Any, AsyncIterator

from loguru import logger

from valor.adapters.llm.protocol import ToolCallingProvider
from valor.adapters.llm.router import get_llm_provider
from valor.runtime.answer import generate_answer
from valor.runtime.supervisor import run_supervisor
from valor.runtime.tools import get_default_tools


def _get_tool_calling_provider() -> ToolCallingProvider:
    """Get the active LLM provider; raise if it doesn't support tool calling."""
    provider = get_llm_provider()
    if not isinstance(provider, ToolCallingProvider):
        raise RuntimeError(
            f"Active LLM provider '{provider.provider_name}' does not support "
            f"tool calling (ToolCallingProvider protocol). Agent Runtime requires "
            f"an OpenAI-compatible provider (set VALOR_LLM_PROVIDER=openai_compat)."
        )
    return provider  # type: ignore[return-value]


async def run_agent_runtime(
    query: str,
    *,
    max_iterations: int = 8,
    model: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Run the Agent Runtime for a user query, yielding SSE events.

    Events emitted:
      - conversation_started (caller emits this)
      - reasoning_started
      - tool_call {id, name, arguments}
      - tool_result {id, name, result, error?}
      - max_iterations_reached (if hit)
      - system_failed (on LLM error)
      - message {content: final_answer}
      - done

    Caller (stream.py) is responsible for conversation_started, thread_started,
    user message echo, conversation persistence, and final done event.
    """
    try:
        provider = _get_tool_calling_provider()
    except RuntimeError as exc:
        yield {"event": "system_failed", "data": {"error": str(exc)}}
        yield {"event": "done", "data": {}}
        return

    yield {"event": "reasoning_started", "data": {}}

    # Stream supervisor events via asyncio.Queue (producer=supervisor task,
    # consumer=this generator). Supervisor runs in background; we yield events
    # as they arrive for true streaming.
    import asyncio

    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def _on_event(evt: dict[str, Any]) -> None:
        await queue.put(evt)

    supervisor_task = asyncio.create_task(run_supervisor(
        query=query,
        tools=get_default_tools(),
        provider=provider,
        on_event=_on_event,
        max_iterations=max_iterations,
        model=model,
    ))

    # Stream supervisor events as they arrive
    while True:
        evt = await queue.get()
        if evt is None:
            break
        yield evt

    await supervisor_task  # ensure task completed
    state = supervisor_task.result()

    # Generate final answer
    try:
        final_answer = await generate_answer(
            supervisor_messages=state.messages,
            user_query=query,
            provider=provider,
        )
    except Exception as exc:
        logger.exception("Answer generation failed")
        yield {
            "event": "system_failed",
            "data": {"error": f"Answer generation failed: {exc}"},
        }
        yield {"event": "done", "data": {}}
        return

    yield {
        "event": "message",
        "data": {
            "role": "agent",
            "payload": {"content": final_answer},
        },
    }

    yield {"event": "reasoning_completed", "data": {}}
    yield {"event": "done", "data": {}}


__all__ = ["run_agent_runtime"]