"""Tests for auth routes: /auth/me, /auth/logout (POST), /refresh."""

from valor.server.envelope import ok


def test_auth_me_returns_default_user(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["id"] == "local"
    assert data["name"] == "本地用户"
    assert "email" in data
    assert "avatar" in data
    assert "created_at" in data
    assert "updated_at" in data


def test_auth_logout_is_post_not_get(client):
    # GET must no longer be the route (404 or 405)
    r_get = client.get("/api/v1/auth/logout")
    assert r_get.status_code == 405

    r = client.post("/api/v1/auth/logout")
    assert r.status_code == 200
    assert r.json() == ok(None)


def test_refresh_returns_tokens(client):
    r = client.post("/api/v1/refresh", json={"refreshToken": "old-token-xyz"})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    data = body["data"]
    assert "access_token" in data
    assert "refresh_token" in data
    assert isinstance(data["access_token"], str)
    assert isinstance(data["refresh_token"], str)


def test_refresh_missing_field_returns_fail(client):
    r = client.post("/api/v1/refresh", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 1
    assert "refreshToken" in body["msg"] or "missing" in body["msg"]
