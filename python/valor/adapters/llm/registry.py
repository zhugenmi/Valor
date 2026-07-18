"""Provider registry for LLM adapters.

License: Apache-2.0 OR GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from __future__ import annotations

from valor.adapters.llm.protocol import LLMProvider

_registry: dict[str, type[LLMProvider]] = {}


def register_provider(name: str, provider_cls: type[LLMProvider]) -> None:
    """Register an LLM provider class."""
    _registry[name] = provider_cls


def get_provider_class(name: str) -> type[LLMProvider] | None:
    """Look up a registered provider class by name."""
    return _registry.get(name)


def list_providers() -> list[str]:
    """Return names of all registered providers."""
    return list(_registry.keys())


# Register built-in providers
from valor.adapters.llm.openai_compat import OpenAICompatProvider  # noqa: E402
from valor.adapters.llm.gemini import GeminiProvider  # noqa: E402
from valor.adapters.llm.ollama import OllamaProvider  # noqa: E402

register_provider("openai", OpenAICompatProvider)
register_provider("openai_compat", OpenAICompatProvider)  # generic alias

# Common OpenAI-compatible provider aliases — each can have its own
# api_key / base_url configured via the settings UI, but share the
# OpenAICompatProvider adapter class.  The env-fallback vars remain
# VALOR_OPENAI_* for all of them (router.get_llm_provider priority:
# explicit arg > VALOR_LLM_PROVIDER > first registered).
register_provider("openrouter", OpenAICompatProvider)
register_provider("deepseek", OpenAICompatProvider)
register_provider("siliconflow", OpenAICompatProvider)
register_provider("azure", OpenAICompatProvider)
register_provider("dashscope", OpenAICompatProvider)

register_provider("gemini", GeminiProvider)
register_provider("ollama", OllamaProvider)

__all__ = ["register_provider", "get_provider_class", "list_providers"]