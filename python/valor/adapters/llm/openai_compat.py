"""OpenAI-compatible API provider.

License: Apache-2.0 OR GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from loguru import logger

from valor.adapters.llm.protocol import (
    LLMProvider,
    Message,
    RuntimeMessage,
    ToolCall,
    ToolCallResponse,
    ToolSchema,
)


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
        self.timeout = float(os.getenv("VALOR_LLM_TIMEOUT", "120"))
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

        async with httpx.AsyncClient(timeout=self.timeout) as client:
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
                logger.error(f"OpenAI API request failed: {type(exc).__name__}: {exc}")
                raise RuntimeError(f"OpenAI API request failed: {type(exc).__name__}: {exc}") from exc

        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected OpenAI API response structure: {exc}") from exc

    async def chat_with_tools(
        self,
        messages: list[RuntimeMessage],
        tools: list[ToolSchema],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tool_choice: str = "auto",
        **kwargs: Any,
    ) -> ToolCallResponse:
        """Chat completion with native tool_calls (OpenAI-compatible API).

        Returns a ToolCallResponse with parsed tool_calls (or None if the
        model finished without requesting tools).
        """
        import json

        model_id = model or self.default_model
        payload: dict[str, Any] = {
            "model": model_id,
            "messages": [m.to_openai_format() for m in messages],
            "tools": [t.to_openai_format() for t in tools],
            "tool_choice": tool_choice,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        payload.update(kwargs)

        url = f"{self.base_url}/chat/completions"
        logger.debug(
            f"OpenAI tool-call API request: {url} (model={model_id}, tools={len(tools)})"
        )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(
                    url,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}",
                    },
                )
                logger.info(f"OpenAI tool-call API response status: {resp.status_code}")
                resp.raise_for_status()
                body = resp.json()
            except httpx.HTTPStatusError as exc:
                logger.error(
                    f"OpenAI tool-call API HTTP error {exc.response.status_code}: "
                    f"{exc.response.text}"
                )
                raise RuntimeError(
                    f"OpenAI tool-call API error {exc.response.status_code}: "
                    f"{exc.response.text}"
                ) from exc
            except httpx.RequestError as exc:
                logger.error(f"OpenAI tool-call API request failed: {type(exc).__name__}: {exc}")
                raise RuntimeError(
                    f"OpenAI tool-call API request failed: {type(exc).__name__}: {exc}"
                ) from exc

        try:
            msg = body["choices"][0]["message"]
            finish_reason = body["choices"][0].get("finish_reason", "stop")
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected OpenAI tool-call response structure: {exc}") from exc

        content = msg.get("content")
        raw_tool_calls = msg.get("tool_calls") or []
        tool_calls: list[ToolCall] = []
        for raw in raw_tool_calls:
            try:
                fn = raw.get("function", {})
                args_str = fn.get("arguments", "{}")
                args = json.loads(args_str) if args_str else {}
                tool_calls.append(
                    ToolCall(
                        id=raw.get("id", ""),
                        name=fn.get("name", ""),
                        arguments=args if isinstance(args, dict) else {},
                    )
                )
            except (json.JSONDecodeError, TypeError) as exc:
                logger.warning(f"Failed to parse tool_call arguments: {exc}; raw={raw}")

        return ToolCallResponse(
            content=content,
            tool_calls=tool_calls if tool_calls else None,
            finish_reason=finish_reason,
        )


def verify() -> None:
    """Verify that OpenAICompatProvider satisfies the LLMProvider protocol."""
    assert isinstance(OpenAICompatProvider, LLMProvider)  # type: ignore[arg-type]


__all__ = ["OpenAICompatProvider", "verify"]