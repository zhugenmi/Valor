"""Tests for /user/profile routes."""


def test_get_empty_profiles(client):
    r = client.get("/api/v1/user/profile")
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    assert body["data"] == {"profiles": []}


def test_delete_nonexistent_profile_is_idempotent(client):
    r = client.delete("/api/v1/user/profile/999")
    assert r.status_code == 200
    assert r.json()["code"] == 0
