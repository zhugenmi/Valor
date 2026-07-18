"""OpenAI-compatible API provider.

License: Apache-2.0 OR GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from loguru import logger

from valor.adapters.llm.protocol import LLMProvider, Message


class OpenAICompatProvider:
    """LLM provider for any OpenAI-compatible API endpoint."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        default_model: str | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("VALOR_OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.api_key = api_key or os.getenv("VALOR_OPENAI_API_KEY", "")
        self.default_model = default_model or os.getenv("VALOR_OPENAI_MODEL", "gpt-4o")
        logger.info(f"OpenAICompatProvider initialized (base_url={self.base_url}, default_model={self.default_model})")

    @property
    def provider_name(self) -> str:
        return "openai"

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
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        payload.update(kwargs)

        url = f"{self.base_url}/chat/completions"
        logger.debug(f"OpenAI API request: {url} (model={model_id})")

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                resp = await client.post(
                    url,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}",
                    },
                )
                logger.info(f"OpenAI API response status: {resp.status_code}")
                resp.raise_for_status()
                body = resp.json()
            except httpx.HTTPStatusError as exc:
                logger.error(f"OpenAI API HTTP error {exc.response.status_code}: {exc.response.text}")
                raise RuntimeError(f"OpenAI API error {exc.response.status_code}: {exc.response.text}") from exc
            except httpx.RequestError as exc:
                logger.error(f"OpenAI API request failed: {exc}")
                raise RuntimeError(f"OpenAI API request failed: {exc}") from exc

        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected OpenAI API response structure: {exc}") from exc


def verify() -> None:
    """Verify that OpenAICompatProvider satisfies the LLMProvider protocol."""
    assert isinstance(OpenAICompatProvider, LLMProvider)  # type: ignore[arg-type]


__all__ = ["OpenAICompatProvider", "verify"]