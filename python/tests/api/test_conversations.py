"""Tests for conversations REST API. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from valor.conversations.models import Conversation, ConversationMessage


@pytest.fixture
def client():
    from fastapi import FastAPI

    from valor.conversations.routes import router

    test_app = FastAPI()
    test_app.include_router(router)
    return TestClient(test_app)


def test_list_conversations_empty(client):
    with patch("valor.conversations.routes.list_conversations", return_value=[]):
        resp = client.get("/api/v1/conversations/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"] == {"conversations": [], "total": 0}


def test_list_conversations_returns_items(client):
    now = datetime.now(UTC).isoformat()
    conv = Conversation(
        id="c1", agent_name="ValorAgent", title="诊断 600519",
        status="completed", portfolio_id="pf_1", ticker="600519",
        created_at=now, updated_at=now,
    )
    with patch("valor.conversations.routes.list_conversations", return_value=[conv]):
        resp = client.get("/api/v1/conversations/")
    body = resp.json()
    assert body["data"]["total"] == 1
    assert body["data"]["conversations"][0]["id"] == "c1"


def test_get_history(client):
    now = datetime.now(UTC).isoformat()
    msgs = [
        ConversationMessage(id="m1", conversation_id="c1", role="user",
                             event_type="message", content="hi",
                             created_at=now, seq=1),
    ]
    with patch("valor.conversations.routes.get_messages", return_value=msgs):
        resp = client.get("/api/v1/conversations/c1/history")
    body = resp.json()
    assert body["data"]["conversation_id"] == "c1"
    assert len(body["data"]["items"]) == 1
    assert body["data"]["items"][0]["data"]["payload"]["content"] == "hi"


def test_delete_conversation(client):
    with patch("valor.conversations.routes._delete_conversation", return_value=True):
        resp = client.delete("/api/v1/conversations/c1")
    assert resp.status_code == 200
    assert resp.json()["code"] == 0
