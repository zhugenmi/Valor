"""Pydantic models for conversation persistence. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

from pydantic import BaseModel


class Conversation(BaseModel):
    id: str
    agent_name: str
    title: str | None = None
    status: str = "active"  # 'active' | 'completed' | 'failed'
    portfolio_id: str | None = None
    ticker: str | None = None
    created_at: str
    updated_at: str


class ConversationMessage(BaseModel):
    id: str
    conversation_id: str
    role: str  # 'user' | 'assistant' | 'system'
    event_type: str | None = None
    content: str | None = None
    created_at: str
    seq: int


__all__ = ["Conversation", "ConversationMessage"]
