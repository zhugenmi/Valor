"""Tests for /tasks/{task_id}/cancel."""


def test_cancel_task_returns_ok(client):
    r = client.post("/api/v1/tasks/some-task-id/cancel")
    assert r.status_code == 200
    assert r.json() == {"code": 0, "data": None, "msg": "ok"}
