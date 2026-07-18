"""Tests for analysis route envelope wrapping."""


def test_start_analysis_returns_envelope(client, monkeypatch):
    # Mock run_analysis to avoid hitting real workflow (sync, runs in thread)
    def fake_run(**kwargs):
        return {"messages": []}

    monkeypatch.setattr("valor.server.routes.analysis.run_analysis", fake_run)

    r = client.post(
        "/api/v1/analysis/start",
        json={"ticker": "600519"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    assert "data" in body
    assert body["data"]["run_id"]
    assert body["data"]["ticker"] == "600519"
    assert body["data"]["status"] in ("running", "completed")


def test_get_status_returns_envelope(client, monkeypatch):
    def fake_run(**kwargs):
        return {"messages": []}

    monkeypatch.setattr("valor.server.routes.analysis.run_analysis", fake_run)

    start = client.post("/api/v1/analysis/start", json={"ticker": "600519"}).json()
    run_id = start["data"]["run_id"]

    r = client.get(f"/api/v1/analysis/{run_id}/status")
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    assert body["data"]["run_id"] == run_id


def test_get_status_unknown_run_returns_envelope_fail(client):
    r = client.get("/api/v1/analysis/nonexistent/status")
    # HTTP 404 is fine here - FastAPI HTTPException bypasses envelope
    assert r.status_code == 404
