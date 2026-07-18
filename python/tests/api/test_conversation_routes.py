"""Tests for conversation route field alignment with frontend types."""


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
