"""SQLite CRUD for conversations. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import List

from valor.conversations.models import Conversation, ConversationMessage
from valor.server.db import get_conn


def create_conversation(conv: Conversation) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO conversations
               (id, agent_name, title, status, portfolio_id, ticker, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (conv.id, conv.agent_name, conv.title, conv.status,
             conv.portfolio_id, conv.ticker, conv.created_at, conv.updated_at),
        )


def append_message(msg: ConversationMessage) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO conversation_messages
               (id, conversation_id, role, event_type, content, created_at, seq)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (msg.id, msg.conversation_id, msg.role, msg.event_type,
             msg.content, msg.created_at, msg.seq),
        )
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (datetime.now(UTC).isoformat(), msg.conversation_id),
        )


def list_conversations(limit: int = 50) -> List[Conversation]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM conversations ORDER BY datetime(updated_at) DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [Conversation.model_validate(dict(r)) for r in rows]


def get_messages(conversation_id: str) -> List[ConversationMessage]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM conversation_messages WHERE conversation_id = ? ORDER BY seq ASC",
            (conversation_id,),
        ).fetchall()
    return [ConversationMessage.model_validate(dict(r)) for r in rows]


def delete_conversation(conversation_id: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM conversations WHERE id = ?", (conversation_id,)
        )
        return cur.rowcount > 0


def update_conversation_status(conversation_id: str, status: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE conversations SET status = ?, updated_at = ? WHERE id = ?",
            (status, datetime.now(UTC).isoformat(), conversation_id),
        )


__all__ = [
    "create_conversation",
    "append_message",
    "list_conversations",
    "get_messages",
    "delete_conversation",
    "update_conversation_status",
]
