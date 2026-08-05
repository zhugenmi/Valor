"""Tests for conversations REST API and route field alignment with frontend types.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from valor.conversations.models import Conversation, ConversationMessage


@pytest.fixture
def conv_client():
    from fastapi import FastAPI

    from valor.conversations.routes import router

    test_app = FastAPI()
    test_app.include_router(router)
    return TestClient(test_app)


def test_list_conversations_empty(conv_client):
    with patch("valor.conversations.routes.list_conversations", return_value=[]):
        resp = conv_client.get("/api/v1/conversations/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"] == {"conversations": [], "total": 0}


def test_list_conversations_returns_items(conv_client):
    now = datetime.now(UTC).isoformat()
    conv = Conversation(
        id="c1", agent_name="ValorAgent", title="诊断 600519",
        status="completed", portfolio_id="pf_1", ticker="600519",
        created_at=now, updated_at=now,
    )
    with patch("valor.conversations.routes.list_conversations", return_value=[conv]):
        resp = conv_client.get("/api/v1/conversations/")
    body = resp.json()
    assert body["data"]["total"] == 1
    assert body["data"]["conversations"][0]["id"] == "c1"


def test_get_history(conv_client):
    now = datetime.now(UTC).isoformat()
    msgs = [
        ConversationMessage(id="m1", conversation_id="c1", role="user",
                             event_type="message", content="hi",
                             created_at=now, seq=1),
    ]
    with patch("valor.conversations.routes.get_messages", return_value=msgs):
        resp = conv_client.get("/api/v1/conversations/c1/history")
    body = resp.json()
    assert body["data"]["conversation_id"] == "c1"
    assert len(body["data"]["items"]) == 1
    assert body["data"]["items"][0]["data"]["payload"]["content"] == "hi"


def test_delete_conversation(conv_client):
    with patch("valor.conversations.routes._delete_conversation", return_value=True):
        resp = conv_client.delete("/api/v1/conversations/c1")
    assert resp.status_code == 200
    assert resp.json()["code"] == 0


# ---------------------------------------------------------------------------
# Route field alignment with frontend types
# ---------------------------------------------------------------------------

def test_history_returns_items_not_messages(client):
    r = client.get("/api/v1/conversations/abc/history")
    assert r.status_code == 200
    data = r.json()["data"]
    assert "items" in data
    assert "messages" not in data


def test_scheduled_results_returns_items_not_runs(client):
    r = client.get("/api/v1/conversations/abc/scheduled-task-results")
    assert r.status_code == 200
    data = r.json()["data"]
    assert "items" in data
    assert "runs" not in data


def test_all_scheduled_results_returns_agents_not_runs(client):
    r = client.get("/api/v1/conversations/scheduled-task-results")
    assert r.status_code == 200
    data = r.json()["data"]
    assert "agents" in data
    assert "runs" not in data