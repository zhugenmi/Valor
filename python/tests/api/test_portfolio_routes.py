"""Tests for portfolio REST routes. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from unittest.mock import AsyncMock, MagicMock
import pandas as pd
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def portfolio_dir(tmp_path, monkeypatch):
    from valor.portfolio import storage
    monkeypatch.setattr(storage, "_data_dir", tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    yield tmp_path


@pytest.fixture
def app_client(portfolio_dir, tmp_db):
    from valor.server.main import app
    return TestClient(app)


@pytest.fixture
def mock_data_router():
    """Set up dependency override for get_data_router."""
    from valor.server.main import app
    from valor.server.routes.portfolio import get_data_router

    m = MagicMock()
    m.get_realtime_quote = AsyncMock(return_value=pd.DataFrame([{"price": "100"}]))
    m.get_financial_indicators = AsyncMock(return_value=pd.DataFrame([{"industry": "白酒"}]))
    m.get_daily_history = AsyncMock(return_value=pd.DataFrame({"close": ["100"] * 100}))
    app.dependency_overrides[get_data_router] = lambda: m
    yield m
    app.dependency_overrides.clear()


def _seed(app_client, name="p"):
    return app_client.post("/api/v1/portfolios", json={"name": name}).json()["data"]["portfolio_id"]


GENERIC_CSV_BYTES = "ticker,name,quantity,cost_price,open_date\n600519,贵州茅台,100,1689.50,2024-03-15\n".encode("utf-8")
EASTMONEY_CSV_BYTES = "证券代码,证券名称,持仓数量,成本价\n600519,贵州茅台,100,1689.50\n".encode("gbk")


# --- Portfolio CRUD ---


def test_create_portfolio(app_client):
    resp = app_client.post("/api/v1/portfolios", json={"name": "主力", "benchmark": "000300", "cash": "50000"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "主力"
    assert data["portfolio_id"].startswith("pf_")


def test_list_portfolios_empty(app_client, mock_data_router):
    resp = app_client.get("/api/v1/portfolios")
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_list_portfolios_after_create(app_client, mock_data_router):
    app_client.post("/api/v1/portfolios", json={"name": "p1"})
    app_client.post("/api/v1/portfolios", json={"name": "p2"})
    resp = app_client.get("/api/v1/portfolios")
    assert len(resp.json()["data"]) == 2


def test_get_portfolio(app_client):
    r = app_client.post("/api/v1/portfolios", json={"name": "p1"}).json()["data"]
    resp = app_client.get(f"/api/v1/portfolios/{r['portfolio_id']}")
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "p1"


def test_get_portfolio_not_found(app_client):
    resp = app_client.get("/api/v1/portfolios/pf_missing")
    assert resp.status_code == 404


def test_update_portfolio(app_client):
    r = app_client.post("/api/v1/portfolios", json={"name": "p1"}).json()["data"]
    resp = app_client.put(f"/api/v1/portfolios/{r['portfolio_id']}", json={"name": "新名", "cash": "10000"})
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "新名"
    assert resp.json()["data"]["cash"] == "10000"


def test_delete_portfolio(app_client):
    r = app_client.post("/api/v1/portfolios", json={"name": "p1"}).json()["data"]
    resp = app_client.delete(f"/api/v1/portfolios/{r['portfolio_id']}")
    assert resp.status_code == 200
    assert app_client.get(f"/api/v1/portfolios/{r['portfolio_id']}").status_code == 404


# --- CSV Import ---


def test_import_csv_generic_merge(app_client):
    r = app_client.post("/api/v1/portfolios", json={"name": "p"}).json()["data"]
    resp = app_client.post(
        f"/api/v1/portfolios/{r['portfolio_id']}/import?mode=merge",
        files={"file": ("holdings.csv", GENERIC_CSV_BYTES, "text/csv")},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["format"] == "generic"
    assert data["imported_rows"] == 1
    get_resp = app_client.get(f"/api/v1/portfolios/{r['portfolio_id']}")
    assert len(get_resp.json()["data"]["holdings"]) == 1


def test_import_csv_eastmoney(app_client):
    r = app_client.post("/api/v1/portfolios", json={"name": "p"}).json()["data"]
    resp = app_client.post(
        f"/api/v1/portfolios/{r['portfolio_id']}/import",
        files={"file": ("em.csv", EASTMONEY_CSV_BYTES, "text/csv")},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["format"] == "eastmoney"
    assert resp.json()["data"]["imported_rows"] == 1


def test_import_csv_replace_mode(app_client):
    r = app_client.post("/api/v1/portfolios", json={"name": "p"}).json()["data"]
    pid = r["portfolio_id"]
    app_client.post(f"/api/v1/portfolios/{pid}/import",
                    files={"file": ("a.csv", GENERIC_CSV_BYTES, "text/csv")})
    app_client.post(f"/api/v1/portfolios/{pid}/import?mode=replace",
                    files={"file": ("b.csv", b"ticker,quantity,cost_price\n000858,200,158.20\n", "text/csv")})
    holdings = app_client.get(f"/api/v1/portfolios/{pid}").json()["data"]["holdings"]
    assert len(holdings) == 1
    assert holdings[0]["ticker"] == "000858"


def test_import_csv_not_found(app_client):
    resp = app_client.post(
        "/api/v1/portfolios/pf_missing/import",
        files={"file": ("a.csv", GENERIC_CSV_BYTES, "text/csv")},
    )
    assert resp.status_code == 404


# --- Holdings CRUD ---


def test_list_holdings_empty(app_client):
    pid = _seed(app_client)
    resp = app_client.get(f"/api/v1/portfolios/{pid}/holdings")
    assert resp.json()["data"] == []


def test_add_holding(app_client):
    pid = _seed(app_client)
    resp = app_client.post(f"/api/v1/portfolios/{pid}/holdings", json={
        "ticker": "600519", "name": "贵州茅台", "lots": [
            {"lot_id": "l1", "open_date": "2024-03-15", "quantity": 100, "cost_price": "1689.50", "fees": "12.50"}
        ]
    })
    assert resp.status_code == 200
    assert resp.json()["data"]["ticker"] == "600519"


def test_update_holding(app_client):
    pid = _seed(app_client)
    app_client.post(f"/api/v1/portfolios/{pid}/holdings", json={
        "ticker": "600519", "lots": []})
    resp = app_client.put(f"/api/v1/portfolios/{pid}/holdings/600519", json={
        "ticker": "600519", "name": "新名", "lots": []})
    # update_holding returns the portfolio; holding name is in holdings[0]
    assert resp.json()["data"]["holdings"][0]["name"] == "新名"


def test_delete_holding(app_client):
    pid = _seed(app_client)
    app_client.post(f"/api/v1/portfolios/{pid}/holdings", json={"ticker": "600519", "lots": []})
    resp = app_client.delete(f"/api/v1/portfolios/{pid}/holdings/600519")
    assert resp.status_code == 200
    assert app_client.get(f"/api/v1/portfolios/{pid}/holdings").json()["data"] == []


def test_add_lot(app_client):
    pid = _seed(app_client)
    app_client.post(f"/api/v1/portfolios/{pid}/holdings", json={"ticker": "600519", "lots": [
        {"lot_id": "l1", "open_date": "2024-01-01", "quantity": 100, "cost_price": "100"}
    ]})
    resp = app_client.post(f"/api/v1/portfolios/{pid}/holdings/600519/lots", json={
        "lot_id": "l2", "open_date": "2024-02-01", "quantity": 50, "cost_price": "110"
    })
    assert resp.status_code == 200
    lots = resp.json()["data"]["lots"]
    assert len(lots) == 2


def test_update_holding_not_found(app_client):
    pid = _seed(app_client)
    resp = app_client.put(f"/api/v1/portfolios/{pid}/holdings/000001", json={"ticker": "000001", "lots": []})
    assert resp.status_code == 404


# --- Analytics ---


def test_analytics_route(app_client, mock_data_router):
    # Override price for this test
    mock_data_router.get_realtime_quote = AsyncMock(return_value=pd.DataFrame([{"price": "110"}]))
    pid = _seed(app_client)
    app_client.post(f"/api/v1/portfolios/{pid}/holdings", json={
        "ticker": "600519", "lots": [
            {"lot_id": "l1", "open_date": "2024-01-01", "quantity": 100, "cost_price": "100"}
        ]
    })
    resp = app_client.get(f"/api/v1/portfolios/{pid}/analytics")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total_market_value"] in ("11000", "11000.0")
    assert data["positions"][0]["ticker"] == "600519"


# --- Strategies ---


def test_create_strategy_route(app_client, mock_data_router):
    pid = _seed(app_client)
    app_client.post(f"/api/v1/portfolios/{pid}/holdings", json={
        "ticker": "600519", "lots": [
            {"lot_id": "l1", "open_date": "2024-01-01", "quantity": 100, "cost_price": "100"}
        ]
    })
    resp = app_client.post(f"/api/v1/portfolios/{pid}/strategies", json={
        "method": "equal_weight", "tickers": ["600519"], "params": {"lookback_days": 30}
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["method"] == "equal_weight"
    assert "strategy_id" in data
    assert data["target_weights"]["600519"] == pytest.approx(1.0)


def test_list_strategies_route(app_client, mock_data_router):
    pid = _seed(app_client)
    app_client.post(f"/api/v1/portfolios/{pid}/strategies", json={
        "method": "equal_weight", "tickers": ["600519"], "params": {"lookback_days": 30}
    })
    resp = app_client.get(f"/api/v1/portfolios/{pid}/strategies")
    assert len(resp.json()["data"]) == 1


def test_delete_strategy_route(app_client, mock_data_router):
    pid = _seed(app_client)
    r = app_client.post(f"/api/v1/portfolios/{pid}/strategies", json={
        "method": "equal_weight", "tickers": ["600519"], "params": {"lookback_days": 30}
    }).json()["data"]
    resp = app_client.delete(f"/api/v1/portfolios/{pid}/strategies/{r['strategy_id']}")
    assert resp.status_code == 200
    assert app_client.get(f"/api/v1/portfolios/{pid}/strategies").json()["data"] == []


# --- Rebalance ---


def test_rebalance_route(app_client, mock_data_router):
    pid = _seed(app_client)
    app_client.post(f"/api/v1/portfolios/{pid}/holdings", json={
        "ticker": "600519", "lots": [
            {"lot_id": "l1", "open_date": "2024-01-01", "quantity": 100, "cost_price": "100"}
        ]
    })
    strat = app_client.post(f"/api/v1/portfolios/{pid}/strategies", json={
        "method": "equal_weight", "tickers": ["600519"], "params": {"lookback_days": 30}
    }).json()["data"]
    rebalance_resp = app_client.post(f"/api/v1/portfolios/{pid}/rebalance", json={
        "strategy_id": strat["strategy_id"], "params": {}
    })
    assert rebalance_resp.status_code == 200
    data = rebalance_resp.json()["data"]
    assert "actions" in data
    assert "cash_after" in data
    assert "total_est_cost" in data


def test_rebalance_strategy_not_found(app_client, mock_data_router):
    pid = _seed(app_client)
    resp = app_client.post(f"/api/v1/portfolios/{pid}/rebalance", json={"strategy_id": "strat_missing", "params": {}})
    assert resp.status_code == 404


# --- Error paths & edge cases (coverage) ---


def test_update_portfolio_not_found(app_client):
    resp = app_client.put("/api/v1/portfolios/pf_missing", json={"name": "x"})
    assert resp.status_code == 404


def test_update_portfolio_all_fields(app_client):
    pid = _seed(app_client)
    resp = app_client.put(f"/api/v1/portfolios/{pid}", json={
        "name": "新名", "benchmark": "000905", "cash": "10000", "meta": {"tag": "test"},
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "新名"
    assert data["benchmark"] == "000905"
    assert data["cash"] == "10000"
    assert data["meta"] == {"tag": "test"}


def test_delete_portfolio_not_found(app_client):
    resp = app_client.delete("/api/v1/portfolios/pf_missing")
    assert resp.status_code == 404


def test_import_csv_unknown_format(app_client):
    pid = _seed(app_client)
    resp = app_client.post(
        f"/api/v1/portfolios/{pid}/import",
        files={"file": ("a.csv", b"col1,col2\nfoo,bar\n", "text/csv")},
    )
    assert resp.status_code == 400


def test_list_holdings_portfolio_not_found(app_client):
    resp = app_client.get("/api/v1/portfolios/pf_missing/holdings")
    assert resp.status_code == 404


def test_add_holding_portfolio_not_found(app_client):
    resp = app_client.post("/api/v1/portfolios/pf_missing/holdings", json={
        "ticker": "600519", "lots": []})
    assert resp.status_code == 404


def test_add_holding_auto_gen_lot_id(app_client):
    pid = _seed(app_client)
    resp = app_client.post(f"/api/v1/portfolios/{pid}/holdings", json={
        "ticker": "600519", "lots": [
            {"lot_id": "", "open_date": "2024-01-01", "quantity": 100, "cost_price": "100"}
        ]
    })
    assert resp.status_code == 200
    lot_id = resp.json()["data"]["lots"][0]["lot_id"]
    assert lot_id.startswith("lot_")


def test_update_holding_portfolio_not_found(app_client):
    resp = app_client.put("/api/v1/portfolios/pf_missing/holdings/600519", json={
        "ticker": "600519", "lots": []})
    assert resp.status_code == 404


def test_delete_holding_portfolio_not_found(app_client):
    resp = app_client.delete("/api/v1/portfolios/pf_missing/holdings/600519")
    assert resp.status_code == 404


def test_delete_holding_not_found(app_client):
    pid = _seed(app_client)
    resp = app_client.delete(f"/api/v1/portfolios/{pid}/holdings/000001")
    assert resp.status_code == 404


def test_add_lot_portfolio_not_found(app_client):
    resp = app_client.post("/api/v1/portfolios/pf_missing/holdings/600519/lots", json={
        "lot_id": "l1", "open_date": "2024-01-01", "quantity": 100, "cost_price": "100"})
    assert resp.status_code == 404


def test_add_lot_holding_not_found(app_client):
    pid = _seed(app_client)
    resp = app_client.post(f"/api/v1/portfolios/{pid}/holdings/000001/lots", json={
        "lot_id": "l1", "open_date": "2024-01-01", "quantity": 100, "cost_price": "100"})
    assert resp.status_code == 404


def test_add_lot_auto_gen_lot_id(app_client):
    pid = _seed(app_client)
    app_client.post(f"/api/v1/portfolios/{pid}/holdings", json={"ticker": "600519", "lots": [
        {"lot_id": "l1", "open_date": "2024-01-01", "quantity": 100, "cost_price": "100"}
    ]})
    resp = app_client.post(f"/api/v1/portfolios/{pid}/holdings/600519/lots", json={
        "lot_id": "", "open_date": "2024-02-01", "quantity": 50, "cost_price": "110"
    })
    assert resp.status_code == 200
    new_lot_id = resp.json()["data"]["lots"][-1]["lot_id"]
    assert new_lot_id.startswith("lot_")


def test_analytics_portfolio_not_found(app_client, mock_data_router):
    resp = app_client.get("/api/v1/portfolios/pf_missing/analytics")
    assert resp.status_code == 404


def test_analytics_historical_exception_fallback(app_client, mock_data_router):
    """When historical lookup raises, analytics falls back to price-only computation."""
    mock_data_router.get_daily_history = AsyncMock(
        return_value=pd.DataFrame({"close": ["100", "not_a_number", "200"]})
    )
    mock_data_router.get_realtime_quote = AsyncMock(
        return_value=pd.DataFrame([{"price": "100"}])
    )
    pid = _seed(app_client)
    app_client.post(f"/api/v1/portfolios/{pid}/holdings", json={
        "ticker": "600519", "lots": [
            {"lot_id": "l1", "open_date": "2024-01-01", "quantity": 100, "cost_price": "100"}
        ]
    })
    resp = app_client.get(f"/api/v1/portfolios/{pid}/analytics")
    assert resp.status_code == 200
    assert resp.json()["data"]["total_market_value"] in ("10000", "10000.0")


def test_create_strategy_portfolio_not_found(app_client, mock_data_router):
    resp = app_client.post("/api/v1/portfolios/pf_missing/strategies", json={
        "method": "equal_weight", "tickers": ["600519"], "params": {"lookback_days": 30}
    })
    assert resp.status_code == 404


def test_list_strategies_portfolio_not_found(app_client):
    resp = app_client.get("/api/v1/portfolios/pf_missing/strategies")
    assert resp.status_code == 404


def test_get_strategy_route(app_client, mock_data_router):
    pid = _seed(app_client)
    created = app_client.post(f"/api/v1/portfolios/{pid}/strategies", json={
        "method": "equal_weight", "tickers": ["600519"], "params": {"lookback_days": 30}
    }).json()["data"]
    resp = app_client.get(f"/api/v1/portfolios/{pid}/strategies/{created['strategy_id']}")
    assert resp.status_code == 200
    assert resp.json()["data"]["strategy_id"] == created["strategy_id"]


def test_get_strategy_not_found(app_client, mock_data_router):
    pid = _seed(app_client)
    resp = app_client.get(f"/api/v1/portfolios/{pid}/strategies/strat_missing")
    assert resp.status_code == 404


def test_get_strategy_portfolio_not_found(app_client):
    resp = app_client.get("/api/v1/portfolios/pf_missing/strategies/strat_x")
    assert resp.status_code == 404


def test_delete_strategy_portfolio_not_found(app_client):
    resp = app_client.delete("/api/v1/portfolios/pf_missing/strategies/strat_x")
    assert resp.status_code == 404


def test_delete_strategy_not_found(app_client, mock_data_router):
    pid = _seed(app_client)
    resp = app_client.delete(f"/api/v1/portfolios/{pid}/strategies/strat_missing")
    assert resp.status_code == 404


def test_rebalance_portfolio_not_found(app_client, mock_data_router):
    resp = app_client.post("/api/v1/portfolios/pf_missing/rebalance", json={
        "strategy_id": "strat_x", "params": {}})
    assert resp.status_code == 404


# --- Lot CRUD ---


def test_update_lot_success(app_client):
    pid = _seed(app_client)
    _seed_holding(app_client, pid)
    p = app_client.get(f"/api/v1/portfolios/{pid}").json()["data"]
    lot_id = p["holdings"][0]["lots"][0]["lot_id"]
    resp = app_client.put(
        f"/api/v1/portfolios/{pid}/holdings/600519/lots/{lot_id}",
        json={"cost_price": "1700.00", "fees": "12.50"},
    )
    assert resp.status_code == 200
    updated_p = resp.json()["data"]
    updated_h = next(x for x in updated_p["holdings"] if x["ticker"] == "600519")
    lot = next(x for x in updated_h["lots"] if x["lot_id"] == lot_id)
    assert lot["cost_price"] == "1700.00"
    assert lot["fees"] == "12.50"
    assert lot["quantity"] == 100


def test_update_lot_quantity_to_zero_removes(app_client):
    pid = _seed(app_client)
    _seed_holding(app_client, pid, qty=100)
    p = app_client.get(f"/api/v1/portfolios/{pid}").json()["data"]
    lot_id = p["holdings"][0]["lots"][0]["lot_id"]
    resp = app_client.put(
        f"/api/v1/portfolios/{pid}/holdings/600519/lots/{lot_id}",
        json={"quantity": 0},
    )
    assert resp.status_code == 200
    assert len(resp.json()["data"]["holdings"]) == 0


def test_update_lot_not_found_404(app_client):
    pid = _seed(app_client)
    _seed_holding(app_client, pid)
    resp = app_client.put(
        f"/api/v1/portfolios/{pid}/holdings/600519/lots/lot_missing",
        json={"quantity": 50},
    )
    assert resp.status_code == 404


def test_update_lot_holding_not_found_404(app_client):
    pid = _seed(app_client)
    resp = app_client.put(
        f"/api/v1/portfolios/{pid}/holdings/000001/lots/lot_x",
        json={"quantity": 50},
    )
    assert resp.status_code == 404


def test_delete_lot_success(app_client):
    pid = _seed(app_client)
    _seed_holding(app_client, pid, qty=100)
    p = app_client.get(f"/api/v1/portfolios/{pid}").json()["data"]
    lot_id = p["holdings"][0]["lots"][0]["lot_id"]
    resp = app_client.delete(
        f"/api/v1/portfolios/{pid}/holdings/600519/lots/{lot_id}",
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["deleted"] == lot_id
    p2 = app_client.get(f"/api/v1/portfolios/{pid}").json()["data"]
    assert len(p2["holdings"]) == 0


def test_delete_lot_keeps_holding_when_has_sell_lots(app_client):
    pid = _seed(app_client)
    _seed_holding(app_client, pid, qty=100)
    app_client.post(
        f"/api/v1/portfolios/{pid}/holdings/600519/sells",
        json={"sell_date": "2026-07-19", "quantity": 50, "sell_price": "1820.00", "fees": "5.00"},
    )
    p = app_client.get(f"/api/v1/portfolios/{pid}").json()["data"]
    lot_id = p["holdings"][0]["lots"][0]["lot_id"]
    resp = app_client.delete(
        f"/api/v1/portfolios/{pid}/holdings/600519/lots/{lot_id}",
    )
    assert resp.status_code == 200
    p2 = app_client.get(f"/api/v1/portfolios/{pid}").json()["data"]
    assert len(p2["holdings"]) == 1
    assert len(p2["holdings"][0]["sell_lots"]) == 1
    assert len(p2["holdings"][0]["lots"]) == 0


def test_delete_lot_not_found_404(app_client):
    pid = _seed(app_client)
    _seed_holding(app_client, pid)
    resp = app_client.delete(
        f"/api/v1/portfolios/{pid}/holdings/600519/lots/lot_missing",
    )
    assert resp.status_code == 404


# --- Sell Lots ---


def _seed_holding(app_client, pid, ticker="600519", qty=100, cost="1689.50"):
    """Helper: add a holding with one lot via API."""
    app_client.post(
        f"/api/v1/portfolios/{pid}/holdings",
        json={
            "ticker": ticker,
            "name": "贵州茅台",
            "side": "long",
            "lots": [{
                "lot_id": "",
                "open_date": "2024-01-01",
                "quantity": qty,
                "cost_price": cost,
                "fees": "0",
            }],
        },
    )


def test_add_sell_success(app_client):
    pid = _seed(app_client)
    _seed_holding(app_client, pid)
    resp = app_client.post(
        f"/api/v1/portfolios/{pid}/holdings/600519/sells",
        json={
            "sell_date": "2026-07-19",
            "quantity": 30,
            "sell_price": "1820.00",
            "fees": "15.00",
            "note": "止盈",
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["sell_id"].startswith("sell_")
    assert data["quantity"] == 30
    assert data["avg_cost_at_sell"] == "1689.50"


def test_add_sell_exceeds_position_400(app_client):
    pid = _seed(app_client)
    _seed_holding(app_client, pid, qty=100)
    resp = app_client.post(
        f"/api/v1/portfolios/{pid}/holdings/600519/sells",
        json={"sell_date": "2026-07-19", "quantity": 200, "sell_price": "1820.00", "fees": "0"},
    )
    assert resp.status_code == 400
    assert "exceeds" in resp.json()["detail"]


def test_add_sell_holding_not_found_404(app_client):
    pid = _seed(app_client)
    resp = app_client.post(
        f"/api/v1/portfolios/{pid}/holdings/000001/sells",
        json={"sell_date": "2026-07-19", "quantity": 10, "sell_price": "10.00", "fees": "0"},
    )
    assert resp.status_code == 404


def test_add_sell_portfolio_not_found_404(app_client):
    resp = app_client.post(
        "/api/v1/portfolios/pf_missing/holdings/600519/sells",
        json={"sell_date": "2026-07-19", "quantity": 10, "sell_price": "10.00", "fees": "0"},
    )
    assert resp.status_code == 404
