"""Core Pydantic protocols shared across agents, portfolio, and backtest layers.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from typing import Literal

from pydantic import BaseModel, Field


SignalType = Literal["bullish", "bearish", "neutral"]
ActionType = Literal["buy", "sell", "hold"]
RoleType = Literal["system", "user", "assistant"]


class Message(BaseModel):
    """Chat message exchanged with LLM providers."""

    role: RoleType
    content: str


class Signal(BaseModel):
    """A single agent's directional opinion on a ticker."""

    agent: str
    signal: SignalType
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


class Action(BaseModel):
    """Final portfolio decision produced by the agent workflow."""

    action: ActionType
    quantity: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    agent_signals: list[Signal]
    reasoning: str