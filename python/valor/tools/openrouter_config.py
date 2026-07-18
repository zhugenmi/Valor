"""LLM client shim - wraps valor's adapter layer for A_Share agent compatibility.

Agents call get_chat_completion(messages) - this delegates to valor.adapters.llm.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from valor.adapters.llm.router import get_llm_provider
from valor.core.protocols import Message


def get_chat_completion(
    messages: list[dict[str, str]],
    model: str | None = None,
    max_retries: int = 3,
    initial_retry_delay: int = 1,
    client_type: str = "auto",
    api_key: str | None = None,
    base_url: str | None = None,
) -> str:
    """Get chat completion from configured LLM provider.

    Delegates to valor.adapters.llm.router.get_llm_provider().

    Args:
        messages: OpenAI-format message list [{"role": "...", "content": "..."}]
        model: Model name (ignored in simplified shim, uses provider default)
        max_retries, initial_retry_delay, client_type, api_key, base_url: Ignored

    Returns:
        Response text string.

    Raises:
        RuntimeError: If no provider is available or the chat call fails.
    """
    import asyncio

    try:
        provider = get_llm_provider()
    except RuntimeError as e:
        logger.error("No LLM provider available: {err}", err=e)
        raise RuntimeError(f"No LLM provider available: {e}") from e

    # Convert dict messages to valor Message objects
    valor_messages: list[Message] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        valor_messages.append(Message(role=role, content=content))  # type: ignore[arg-type]

    try:
        response = asyncio.run(provider.chat(valor_messages))
        return response
    except Exception as e:
        logger.error("LLM chat failed: {err}", err=e)
        raise RuntimeError(f"LLM chat failed: {e}") from e


# Also export as generate_content_with_retry for backward compat
def generate_content_with_retry(
    model: Any,
    contents: Any,
    config: Any = None,
) -> Any:
    """Legacy stub - original Gemini-specific function."""
    logger.warning("generate_content_with_retry not implemented in valor shim")
    return None
