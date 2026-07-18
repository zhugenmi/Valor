"""Thin LLM client wrapper preserving A_Share-era function names.

Agents migrated from A_Share call get_llm()/call_llm() - this module delegates
to valor.adapters.llm without requiring agent code changes.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

import asyncio

from valor.adapters.llm import LLMProvider, get_llm_provider
from valor.core.protocols import Message


def get_llm() -> LLMProvider:
    """Return the active LLM provider (sync)."""
    return get_llm_provider()


def call_llm(prompt: str, system: str | None = None) -> str:
    """Send a prompt to the LLM and return the response text (sync).

    Async-adapter for use in synchronous agent code.
    """
    provider = get_llm_provider()
    messages: list[Message] = []
    if system:
        messages.append(Message(role="system", content=system))
    messages.append(Message(role="user", content=prompt))
    return asyncio.run(provider.chat(messages))
