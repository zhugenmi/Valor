"""Runtime state types for Agent Runtime.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from valor.adapters.llm.protocol import RuntimeMessage


@dataclass
class ToolResult:
    """Result of executing one tool call."""

    tool_call_id: str
    name: str
    arguments: dict[str, Any]
    result: dict[str, Any]
    error: str | None = None


@dataclass
class RuntimeState:
    """Mutable state for one Supervisor loop run."""

    messages: list[RuntimeMessage] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    iterations: int = 0
    max_iterations: int = 8
    finished: bool = False
    final_answer: str | None = None


__all__ = ["RuntimeState", "ToolResult"]