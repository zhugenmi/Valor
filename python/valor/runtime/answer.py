"""Final answer generator: synthesize a Markdown reply from Supervisor state.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
from __future__ import annotations

from loguru import logger

from valor.adapters.llm.protocol import Message, RuntimeMessage, ToolCallingProvider
from valor.adapters.llm.router import get_llm_provider

_ANSWER_SYSTEM_PROMPT = """你是 ValorAgent 的最终答复生成器。

基于 Supervisor 的对话历史与工具调用结果，用中文 Markdown 生成对用户的最终答复。

要求：
- 综合所有工具结果，不要遗漏关键信息
- 引用知识库内容时标注 [编号]
- 股票分析结果要包含 action (buy/sell/hold)、confidence、关键 reasoning
- 200-800 字之间，结构清晰
- 如果工具结果有 error，向用户解释失败原因并给建议"""


async def generate_answer(
    supervisor_messages: list[RuntimeMessage],
    user_query: str,
    provider: ToolCallingProvider | None = None,
) -> str:
    """Generate the final user-facing reply from Supervisor state.

    Uses chat_with_tools provider's chat() if available, else falls back to
    get_llm_provider().chat(). Returns a Markdown string.
    """
    # Compress supervisor messages into a context summary
    context_parts: list[str] = []
    for msg in supervisor_messages:
        if msg.role == "user":
            context_parts.append(f"【用户问题】\n{msg.content}")
        elif msg.role == "assistant" and msg.content:
            context_parts.append(f"【Supervisor 思考】\n{msg.content}")
        elif msg.role == "tool":
            context_parts.append(f"【工具结果 {msg.name}】\n{msg.content}")
    context = "\n\n".join(context_parts) or "(无工具调用历史)"

    messages = [
        Message(role="system", content=_ANSWER_SYSTEM_PROMPT),
        Message(role="user", content=f"用户原始问题：{user_query}\n\n--- Supervisor 上下文 ---\n{context}"),
    ]

    # Prefer the ToolCallingProvider's underlying chat; fall back to default LLMProvider
    if provider is not None and hasattr(provider, "chat"):
        try:
            return await provider.chat(messages=messages, temperature=0.3, max_tokens=1024)  # type: ignore[arg-type]
        except Exception as exc:
            logger.warning(f"Answer generation via ToolCallingProvider failed: {exc}; falling back")

    try:
        fallback = get_llm_provider()
        return await fallback.chat(messages=messages, temperature=0.3, max_tokens=1024)
    except Exception as exc:
        logger.exception("Answer generation failed entirely")
        return f"（答复生成失败：{exc}）请稍后重试。"


__all__ = ["generate_answer"]