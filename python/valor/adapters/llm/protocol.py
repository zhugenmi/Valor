"""LLM provider protocol and base types.

License: Apache-2.0 OR GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from __future__ import annotations

import json
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

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


# ---------------------------------------------------------------------------
# Phase 3 Agent Runtime: tool-calling extension (additive, optional)
# ---------------------------------------------------------------------------


class ToolCall(BaseModel):
    """A single tool call requested by the LLM."""

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolCallResponse(BaseModel):
    """LLM response that may contain tool calls."""

    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    finish_reason: str = "stop"


class ToolSchema(BaseModel):
    """JSON-schema-based tool definition (OpenAI function-calling format)."""

    name: str
    description: str
    parameters: dict[str, Any]

    def to_openai_format(self) -> dict[str, Any]:
        """Convert to OpenAI API `tools` array entry format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class RuntimeMessage(BaseModel):
    """Chat message supporting tool_calls and tool results (OpenAI-compatible)."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None

    def to_openai_format(self) -> dict[str, Any]:
        """Convert to OpenAI API `messages` array entry format."""
        msg: dict[str, Any] = {"role": self.role}
        if self.content is not None:
            msg["content"] = self.content
        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                    },
                }
                for tc in self.tool_calls
            ]
        if self.tool_call_id is not None:
            msg["tool_call_id"] = self.tool_call_id
        if self.name is not None:
            msg["name"] = self.name
        return msg


@runtime_checkable
class ToolCallingProvider(Protocol):
    """Extension protocol for LLM providers that support native tool calling.

    Providers implementing this protocol can be used by the Agent Runtime
    (Phase 3). OpenAICompatProvider implements it; GeminiProvider and
    OllamaProvider do not (Runtime will raise an informative error if the
    active provider doesn't support tool calling).
    """

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
    ) -> ToolCallResponse: ...


__all__ = [
    "LLMProvider",
    "Message",
    "RuntimeMessage",
    "ToolCall",
    "ToolCallResponse",
    "ToolSchema",
    "ToolCallingProvider",
]