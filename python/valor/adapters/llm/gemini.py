"""Google Gemini API provider.

License: Apache-2.0 OR GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from loguru import logger

from valor.adapters.llm.protocol import LLMProvider, Message


class GeminiProvider:
    """LLM provider for Google Gemini API."""

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str = "gemini-2.5-flash",
    ) -> None:
        self.api_key = api_key or os.getenv("VALOR_GEMINI_API_KEY", "")
        self.default_model = default_model
        self.timeout = float(os.getenv("VALOR_LLM_TIMEOUT", "120"))
        logger.info(f"GeminiProvider initialized (default_model={self.default_model})")

    @property
    def provider_name(self) -> str:
        return "gemini"

    async def chat(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        # Convert messages to Gemini format
        contents: list[dict[str, Any]] = []
        system_instruction: str | None = None

        for m in messages:
            if m.role == "system":
                system_instruction = m.content
            else:
                role = "model" if m.role == "assistant" else "user"
                contents.append({
                    "role": role,
                    "parts": [{"text": m.content}],
                })

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        model_id = model or self.default_model
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent"
        )
        logger.debug(f"Gemini API request: {url} (model={model_id})")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    params={"key": self.api_key},
                )
                logger.info(f"Gemini API response status: {resp.status_code}")
                resp.raise_for_status()
                body = resp.json()
            except httpx.HTTPStatusError as exc:
                logger.error(f"Gemini API HTTP error {exc.response.status_code}: {exc.response.text}")
                raise RuntimeError(f"Gemini API error {exc.response.status_code}: {exc.response.text}") from exc
            except httpx.RequestError as exc:
                logger.error(f"Gemini API request failed: {exc}")
                raise RuntimeError(f"Gemini API request failed: {exc}") from exc

        try:
            return body["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected Gemini API response structure: {exc}") from exc


def verify() -> None:
    """Verify that GeminiProvider satisfies the LLMProvider protocol."""
    assert isinstance(GeminiProvider, LLMProvider)  # type: ignore[arg-type]


__all__ = ["GeminiProvider", "verify"]