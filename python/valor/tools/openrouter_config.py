"""LLM client shim - wraps valor's adapter layer for A_Share agent compatibility.

Agents call get_chat_completion(messages) - this delegates to valor.adapters.llm.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
from loguru import logger

from valor.adapters.llm.router import get_llm_provider
from valor.core.protocols import Message


_RETRYABLE_CAUSES = (
    httpx.ReadTimeout,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
    httpx.PoolTimeout,
    httpx.ConnectTimeout,
)


def _is_retryable(exc: BaseException) -> bool:
    """Return True if the exception (or its __cause__) is a retryable network error."""
    if isinstance(exc, _RETRYABLE_CAUSES):
        return True
    cause = exc.__cause__
    if isinstance(cause, _RETRYABLE_CAUSES):
        return True
    return False


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

    Delegates to valor.adapters.llm.router.get_llm_provider(). Retries on
    transient network errors (ReadTimeout/ConnectError/RemoteProtocolError)
    with exponential backoff. Non-retryable errors (4xx/5xx HTTPStatusError,
    provider unavailable) raise immediately.

    Args:
        messages: OpenAI-format message list [{"role": "...", "content": "..."}]
        model: Model name (ignored in simplified shim, uses provider default)
        max_retries: Max retry attempts on transient network errors. Default 3.
        initial_retry_delay: Base delay in seconds for exponential backoff. Default 1.
        client_type, api_key, base_url: Ignored

    Returns:
        Response text string.

    Raises:
        RuntimeError: If no provider is available or the chat call fails
            after exhausting retries.
    """
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

    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = asyncio.run(provider.chat(valor_messages))
            return response
        except Exception as exc:
            last_exc = exc
            if not _is_retryable(exc):
                raise RuntimeError(f"LLM chat failed: {exc}") from exc
            if attempt < max_retries - 1:
                delay = initial_retry_delay * (2 ** attempt)
                logger.warning(
                    "LLM 调用网络错误 (attempt={}/{})，{}s 后重试: {}",
                    attempt + 1,
                    max_retries,
                    delay,
                    exc,
                )
                time.sleep(delay)
            else:
                logger.error(
                    "LLM 调用网络错误，已耗尽 {} 次重试: {}",
                    max_retries,
                    exc,
                )

    raise RuntimeError(
        f"LLM chat failed after {max_retries} retries: {last_exc}"
    ) from last_exc


# Also export as generate_content_with_retry for backward compat
def generate_content_with_retry(
    model: Any,
    contents: Any,
    config: Any = None,
) -> Any:
    """Legacy stub - original Gemini-specific function."""
    logger.warning("generate_content_with_retry not implemented in valor shim")
    return None
