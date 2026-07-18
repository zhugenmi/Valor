"""LLM provider protocol and base types.

License: Apache-2.0 OR GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from valor.core.protocols import Message


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM provider adapters.

    Each provider implements chat completion via its own API.
    """

    @property
    def provider_name(self) -> str: ...

    async def chat(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str: ...


__all__ = ["LLMProvider", "Message"]