"""Supervisor loop: LLM tool_calls <-> Executor.

The Supervisor asks the LLM what to do; if the LLM requests tools, the
Supervisor executes them and feeds results back; this loops until the LLM
stops requesting tools (or max_iterations is hit). The final answer is
generated separately by ``answer.generate_answer``.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from loguru import logger

from valor.adapters.llm.protocol import (
    RuntimeMessage,
    ToolCallResponse,
    ToolCallingProvider,
    ToolSchema,
)
from valor.runtime.tools import Tool, execute_tool
from valor.runtime.types import RuntimeState, ToolResult

# Event callback: async fn(event_dict) -> None
EventCallback = Callable[[dict[str, Any]], Awaitable[None]]

_SUPERVISOR_SYSTEM_PROMPT = """你是 ValorAgent，一个 A 股投资分析助手的主编排器（Supervisor）。

你通过调用工具（tools）来回答用户问题。可用工具：
- kb_search: 搜索知识库（研究报告、披露文档、监管文件）
- get_stock_data: 获取股票实时行情 + 财务指标
- run_single_agent: 运行单个分析维度（技术面/基本面/估值/资金面/宏观行业）
- run_full_analysis: 运行完整 9 节点分析工作流（诊断、买卖决策）

调用原则：
1. 纯闲聊（如"你好"、"你是谁"）不要调用工具，直接回复。
2. 用户提到具体股票代码并要求分析时，调用 run_full_analysis 或 run_single_agent。
3. 用户问宏观/行业/政策类问题（无个股），调用 run_single_agent with agent_name="macro_industry"。
4. 用户问及研究报告、披露文档内容时，先调用 kb_search。
5. 需要当前价格、PE、PB 等指标时，调用 get_stock_data。
6. 单次回复最多调用 4 次工具，避免冗余。
7. 工具返回错误时，向用户解释限制并给出建议，不要重试同一工具超过 2 次。

回答用中文，使用 Markdown 格式。"""


def _get_tool_by_name(tools: list[Tool], name: str) -> Tool | None:
    for t in tools:
        if t.schema.name == name:
            return t
    return None


async def run_supervisor(
    query: str,
    tools: list[Tool],
    provider: ToolCallingProvider,
    on_event: EventCallback,
    *,
    max_iterations: int = 8,
    model: str | None = None,
    temperature: float = 0.3,
) -> RuntimeState:
    """Run the Supervisor loop.

    Args:
        query: User's natural-language query.
        tools: Registered tools the Supervisor may call.
        provider: LLM provider implementing ToolCallingProvider.
        on_event: Async callback for SSE events (tool_call, tool_result, etc.).
        max_iterations: Hard stop to prevent infinite loops.
        model: Override LLM model name.
        temperature: LLM temperature (low = more deterministic).

    Returns:
        Final RuntimeState with all messages + tool_results.
    """
    state = RuntimeState(max_iterations=max_iterations)
    state.messages = [
        RuntimeMessage(role="system", content=_SUPERVISOR_SYSTEM_PROMPT),
        RuntimeMessage(role="user", content=query),
    ]

    tool_schemas: list[ToolSchema] = [t.schema for t in tools]

    while state.iterations < state.max_iterations:
        state.iterations += 1
        logger.info(f"Supervisor iteration {state.iterations}/{state.max_iterations}")

        try:
            response: ToolCallResponse = await provider.chat_with_tools(
                messages=state.messages,
                tools=tool_schemas,
                model=model,
                temperature=temperature,
                max_tokens=2048,
            )
        except Exception as exc:
            logger.exception("Supervisor LLM call failed")
            await on_event({
                "event": "system_failed",
                "data": {"error": f"Supervisor LLM call failed: {exc}"},
            })
            state.finished = True
            return state

        # Append assistant message (with tool_calls if any) to conversation
        state.messages.append(RuntimeMessage(
            role="assistant",
            content=response.content,
            tool_calls=response.tool_calls,
        ))

        # No tool calls -> Supervisor is ready to answer
        if not response.tool_calls:
            logger.info("Supervisor finished (no tool_calls); ready for answer generation")
            state.finished = True
            return state

        # Execute each tool call sequentially
        for tc in response.tool_calls:
            await on_event({
                "event": "tool_call",
                "data": {
                    "id": tc.id,
                    "name": tc.name,
                    "arguments": tc.arguments,
                },
            })

            tool = _get_tool_by_name(tools, tc.name)
            if tool is None:
                error_msg = f"Tool '{tc.name}' is not registered"
                logger.warning(error_msg)
                result_dict: dict[str, Any] = {"error": error_msg}
            else:
                result_dict = await execute_tool(tool, tc.arguments)

            tool_result = ToolResult(
                tool_call_id=tc.id,
                name=tc.name,
                arguments=tc.arguments,
                result=result_dict,
                error=result_dict.get("error"),
            )
            state.tool_results.append(tool_result)

            await on_event({
                "event": "tool_result",
                "data": {
                    "id": tc.id,
                    "name": tc.name,
                    "result": result_dict,
                    "error": tool_result.error,
                },
            })

            # Append tool result message to conversation
            state.messages.append(RuntimeMessage(
                role="tool",
                content=json.dumps(result_dict, ensure_ascii=False, default=str),
                tool_call_id=tc.id,
                name=tc.name,
            ))

    # Hit max_iterations
    logger.warning(f"Supervisor hit max_iterations={max_iterations}; stopping")
    await on_event({
        "event": "max_iterations_reached",
        "data": {"iterations": state.iterations, "max": state.max_iterations},
    })
    state.finished = True
    return state


__all__ = ["EventCallback", "run_supervisor"]