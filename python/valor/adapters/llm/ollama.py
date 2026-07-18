"""Ollama local LLM provider.

License: Apache-2.0 OR GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from loguru import logger

from valor.adapters.llm.protocol import LLMProvider, Message


class OllamaProvider:
    """LLM provider for local Ollama models."""

    def __init__(
        self,
        base_url: str | None = None,
        default_model: str = "llama3.2",
    ) -> None:
        self.base_url = (base_url or os.getenv("VALOR_OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.default_model = default_model
        logger.info(f"OllamaProvider initialized (base_url={self.base_url}, default_model={self.default_model})")

    @property
    def provider_name(self) -> str:
        return "ollama"

    async def chat(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        model_id = model or self.default_model
        payload = {
            "model": model_id,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        payload["options"].update(kwargs)

        url = f"{self.base_url}/api/chat"
        logger.debug(f"Ollama API request: {url} (model={model_id})")

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                resp = await client.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                logger.info(f"Ollama API response status: {resp.status_code}")
                resp.raise_for_status()
                body = resp.json()
            except httpx.HTTPStatusError as exc:
                logger.error(f"Ollama API HTTP error {exc.response.status_code}: {exc.response.text}")
                raise RuntimeError(f"Ollama API error {exc.response.status_code}: {exc.response.text}") from exc
            except httpx.RequestError as exc:
                logger.error(f"Ollama API request failed: {exc}")
                raise RuntimeError(f"Ollama API request failed: {exc}") from exc

        try:
            return body["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise RuntimeError(f"Unexpected Ollama API response structure: {exc}") from exc


def verify() -> None:
    """Verify that OllamaProvider satisfies the LLMProvider protocol."""
    assert isinstance(OllamaProvider, LLMProvider)  # type: ignore[arg-type]


__all__ = ["OllamaProvider", "verify"]