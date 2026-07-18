"""LLM provider router with environment-based provider selection.

License: Apache-2.0 OR GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from __future__ import annotations

import os
from typing import Any

from valor.adapters.llm.protocol import LLMProvider
from valor.adapters.llm.registry import get_provider_class, list_providers


def get_llm_provider(
    provider: str | None = None,
    **kwargs: Any,
) -> LLMProvider:
    """Return an LLM provider instance.

    Provider selection priority:
    1. Explicit ``provider`` argument
    2. ``VALOR_LLM_PROVIDER`` environment variable
    3. First registered provider (openai)

    Extra ``kwargs`` are forwarded to the provider constructor.
    """
    name = provider or os.getenv("VALOR_LLM_PROVIDER", "openai")

    cls = get_provider_class(name)
    if cls is None:
        available = list_providers()
        raise RuntimeError(
            f"no LLM provider available: unknown provider '{name}'. "
            f"Available providers: {available or 'none registered'}"
        )

    instance = cls(**kwargs)
    if not isinstance(instance, LLMProvider):
        raise TypeError(f"Provider '{name}' does not satisfy LLMProvider protocol")

    return instance


__all__ = ["get_llm_provider"]