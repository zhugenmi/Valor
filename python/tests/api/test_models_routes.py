"""Tests for /models/providers/* routes."""

import pytest


def test_list_providers_returns_registry(client):
    # list_providers() may return [] if no providers registered in test env,
    # but the route should still return code=0 with a list
    r = client.get("/api/v1/models/providers")
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    assert isinstance(body["data"], list)


def test_get_provider_detail_unknown_returns_404(client):
    r = client.get("/api/v1/models/providers/nonexistent_provider")
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 404


def test_put_config_then_get_detail(client):
    # Use a provider name that exists in registry or seed; skip if none
    providers = client.get("/api/v1/models/providers").json()["data"]
    if not providers:
        pytest.skip("no providers registered")
    provider = providers[0]["provider"]

    r = client.put(
        f"/api/v1/models/providers/{provider}/config",
        json={"api_key": "sk-test", "base_url": "https://api.example.com"},
    )
    assert r.status_code == 200
    assert r.json()["code"] == 0

    r = client.get(f"/api/v1/models/providers/{provider}")
    detail = r.json()["data"]
    assert detail["api_key"] == "sk-test"
    assert detail["base_url"] == "https://api.example.com"


def test_add_and_delete_model(client):
    providers = client.get("/api/v1/models/providers").json()["data"]
    if not providers:
        pytest.skip("no providers registered")
    provider = providers[0]["provider"]

    r = client.post(
        f"/api/v1/models/providers/{provider}/models",
        json={"model_id": "gpt-4o", "model_name": "GPT-4o"},
    )
    assert r.status_code == 200
    assert r.json()["code"] == 0

    detail = client.get(f"/api/v1/models/providers/{provider}").json()["data"]
    assert any(m["model_id"] == "gpt-4o" for m in detail["models"])

    r = client.delete(
        f"/api/v1/models/providers/{provider}/models?model_id=gpt-4o"
    )
    assert r.status_code == 200

    detail = client.get(f"/api/v1/models/providers/{provider}").json()["data"]
    assert not any(m["model_id"] == "gpt-4o" for m in detail["models"])


def test_set_default_provider(client):
    providers = client.get("/api/v1/models/providers").json()["data"]
    if len(providers) < 2:
        pytest.skip("need 2+ providers")
    provider = providers[1]["provider"]

    r = client.put("/api/v1/models/providers/default", json={"provider": provider})
    assert r.status_code == 200

    providers_after = client.get("/api/v1/models/providers").json()["data"]
    defaults = [p for p in providers_after if p["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["provider"] == provider


def test_set_default_model(client):
    providers = client.get("/api/v1/models/providers").json()["data"]
    if not providers:
        pytest.skip("no providers registered")
    provider = providers[0]["provider"]

    client.put(
        f"/api/v1/models/providers/{provider}/default-model",
        json={"model_id": "test-model-id"},
    )
    detail = client.get(f"/api/v1/models/providers/{provider}").json()["data"]
    assert detail["default_model_id"] == "test-model-id"


def test_check_model_success(client, monkeypatch):
    providers = client.get("/api/v1/models/providers").json()["data"]
    if not providers:
        pytest.skip("no providers registered")
    provider = providers[0]["provider"]

    class FakeProvider:
        async def chat(self, **kwargs):
            return "pong"

    monkeypatch.setattr(
        "valor.server.routes.models.get_llm_provider",
        lambda *a, **k: FakeProvider(),
    )

    r = client.post(
        "/api/v1/models/check",
        json={"provider": provider, "model_id": "test", "api_key": "sk-x"},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["ok"] is True
    assert data["provider"] == provider


def test_check_model_failure(client, monkeypatch):
    providers = client.get("/api/v1/models/providers").json()["data"]
    if not providers:
        pytest.skip("no providers registered")
    provider = providers[0]["provider"]

    class FakeProvider:
        async def chat(self, **kwargs):
            raise RuntimeError("auth failed")

    monkeypatch.setattr(
        "valor.server.routes.models.get_llm_provider",
        lambda *a, **k: FakeProvider(),
    )

    r = client.post(
        "/api/v1/models/check",
        json={"provider": provider, "model_id": "test", "api_key": "sk-x"},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["ok"] is False
    assert "auth failed" in data["error"]
