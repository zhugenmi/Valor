"""Tests for /system/default-tickers."""


def test_default_tickers_cn_region(client):
    r = client.get("/api/v1/system/default-tickers?region=cn&language=zh")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["region"] == "cn"
    assert len(data["tickers"]) == 3
    assert all("ticker" in t and "symbol" in t and "name" in t for t in data["tickers"])


def test_default_tickers_default_region(client):
    # No region + language=en infers "default"
    r = client.get("/api/v1/system/default-tickers?language=en")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["region"] == "default"
    assert len(data["tickers"]) >= 3
