"""Tests for stock routes: historical, price, detail."""

import pandas as pd
import pytest


class FakeDataRouter:
    """In-memory DataRouter stub for tests."""

    def __init__(self):
        self.quote_df = pd.DataFrame(
            [{"代码": "600519", "名称": "贵州茅台", "最新价": 1685.0, "涨跌幅": 1.2, "市值": 2.1e12}]
        )
        self.history_df = pd.DataFrame(
            [
                {"date": "2026-07-01", "close": 1680.0},
                {"date": "2026-07-02", "close": 1685.0},
            ]
        )
        self.indicators_df = pd.DataFrame(
            [{"行业": "白酒", "市盈率": 30.5, "市净率": 12.0}]
        )
        self.raise_on_quote = False

    async def get_realtime_quote(self, ticker):
        if self.raise_on_quote:
            raise RuntimeError("boom")
        return self.quote_df

    async def get_daily_history(self, ticker, start, end):
        return self.history_df

    async def get_financial_indicators(self, ticker):
        return self.indicators_df


@pytest.fixture
def fake_router(client):
    """Replace app.state.data_router with a FakeDataRouter."""
    from valor.server.main import app

    fake = FakeDataRouter()
    app.state.data_router = fake
    yield fake


def test_price_historical_returns_array(client, fake_router):
    r = client.get(
        "/api/v1/watchlist/asset/600519/price/historical"
        "?interval=1d&start_date=2026-07-01&end_date=2026-07-02"
    )
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    data = body["data"]
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["time"] == "2026-07-01"
    assert data[0]["price"] == 1680.0


def test_price_historical_rejects_non_1d_interval(client, fake_router):
    r = client.get(
        "/api/v1/watchlist/asset/600519/price/historical"
        "?interval=1m&start_date=2026-07-01&end_date=2026-07-02"
    )
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 1
    assert "1d" in body["msg"]


def test_price_uses_data_router(client, fake_router):
    r = client.get("/api/v1/watchlist/asset/600519/price")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["ticker"] == "600519"
    assert data["price"] == 1685.0
    assert data["currency"] == "CNY"


def test_price_falls_back_when_data_router_fails(client, fake_router):
    fake_router.raise_on_quote = True
    r = client.get("/api/v1/watchlist/asset/600519/price")
    assert r.status_code == 200
    data = r.json()["data"]
    # Stub fallback: price 0.0 but route still returns 200
    assert data["price"] == 0.0
    assert data["source"] == "stub"


def test_stock_detail_uses_data_router(client, fake_router):
    r = client.get("/api/v1/watchlist/asset/600519")
    assert r.status_code == 200
    props = r.json()["data"]["properties"]
    # FakeDataRouter.indicators_df has 行业, 市盈率, 市净率 - route maps them
    assert props["pe_ratio"] == 30.5
