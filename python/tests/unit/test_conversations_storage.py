"""Tests for conversations storage. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from valor.conversations.models import Conversation, ConversationMessage
from valor.conversations.storage import (
    append_message,
    create_conversation,
    delete_conversation,
    get_messages,
    list_conversations,
    update_conversation_status,
)


def _conn_factory():
    """Use in-memory SQLite per-test."""
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@pytest.fixture
def fresh_db():
    """Patch get_conn to yield an in-memory DB with schema applied."""
    schema = """
    CREATE TABLE conversations (
      id TEXT PRIMARY KEY,
      agent_name TEXT NOT NULL,
      title TEXT,
      status TEXT NOT NULL,
      portfolio_id TEXT,
      ticker TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    CREATE TABLE conversation_messages (
      id TEXT PRIMARY KEY,
      conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
      role TEXT NOT NULL,
      event_type TEXT,
      content TEXT,
      created_at TEXT NOT NULL,
      seq INTEGER NOT NULL
    );
    """
    conn = _conn_factory()
    conn.executescript(schema)
    yield conn
    conn.close()


def _patch_conn(fresh_db):
    from contextlib import contextmanager

    @contextmanager
    def fake_conn():
        yield fresh_db

    return patch("valor.conversations.storage.get_conn", fake_conn)


def test_create_and_list_conversation(fresh_db):
    now = datetime.now(UTC).isoformat()
    conv = Conversation(
        id="c1", agent_name="ValorAgent", title="诊断 600519",
        status="active", portfolio_id="pf_1", ticker="600519",
        created_at=now, updated_at=now,
    )
    with _patch_conn(fresh_db):
        create_conversation(conv)
        result = list_conversations()
    assert len(result) == 1
    assert result[0].id == "c1"
    assert result[0].portfolio_id == "pf_1"
    assert result[0].ticker == "600519"


def test_append_message_and_get_messages(fresh_db):
    now = datetime.now(UTC).isoformat()
    conv = Conversation(
        id="c1", agent_name="ValorAgent", title=None,
        status="active", portfolio_id=None, ticker=None,
        created_at=now, updated_at=now,
    )
    with _patch_conn(fresh_db):
        create_conversation(conv)
        m1 = ConversationMessage(
            id="m1", conversation_id="c1", role="user", event_type="message",
            content="诊断股票600519", created_at=now, seq=1,
        )
        m2 = ConversationMessage(
            id="m2", conversation_id="c1", role="assistant", event_type="agent_completed",
            content='{"agent":"technicals"}', created_at=now, seq=2,
        )
        append_message(m1)
        append_message(m2)
        msgs = get_messages("c1")
    assert [m.seq for m in msgs] == [1, 2]
    assert msgs[0].content == "诊断股票600519"


def test_delete_conversation_cascades_messages(fresh_db):
    now = datetime.now(UTC).isoformat()
    conv = Conversation(
        id="c1", agent_name="ValorAgent", title=None,
        status="active", portfolio_id=None, ticker=None,
        created_at=now, updated_at=now,
    )
    with _patch_conn(fresh_db):
        create_conversation(conv)
        append_message(ConversationMessage(
            id="m1", conversation_id="c1", role="user", event_type="message",
            content="hi", created_at=now, seq=1,
        ))
        deleted = delete_conversation("c1")
        assert deleted is True
        assert get_messages("c1") == []


def test_update_status(fresh_db):
    now = datetime.now(UTC).isoformat()
    conv = Conversation(
        id="c1", agent_name="ValorAgent", title=None,
        status="active", portfolio_id=None, ticker=None,
        created_at=now, updated_at=now,
    )
    with _patch_conn(fresh_db):
        create_conversation(conv)
        update_conversation_status("c1", "completed")
        listed = list_conversations()
    assert listed[0].status == "completed"


def test_delete_nonexistent_returns_false(fresh_db):
    with _patch_conn(fresh_db):
        assert delete_conversation("nope") is False
