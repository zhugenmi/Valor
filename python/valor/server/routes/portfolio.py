"""Portfolio REST routes. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Request
from pydantic import BaseModel
from valor.portfolio import storage
from valor.portfolio.models import Portfolio, Holding, Lot, Strategy
from valor.portfolio.loader import parse_generic_csv, parse_eastmoney_csv, detect_format
from valor.portfolio.analytics import compute_analytics
from valor.portfolio.adapters import DataRouterPriceLookup, DataRouterHistoricalLookup, DataRouterSectorLookup
from valor.portfolio.allocator import allocate, AllocatorParams
from valor.portfolio.rebalance import suggest_rebalance, RebalanceParams
from valor.server.envelope import ok
from valor.adapters.data.router import DataRouter

router = APIRouter(prefix="/api/v1/portfolios", tags=["portfolio"])


def get_data_router(request: Request) -> DataRouter:
    router_obj = getattr(request.app.state, "data_router", None)
    if router_obj is None:
        raise HTTPException(status_code=500, detail="DataRouter not initialized")
    return router_obj


class PortfolioCreate(BaseModel):
    name: str
    benchmark: str = "000300"
    cash: Decimal = Decimal("0")
    meta: dict = {}


class PortfolioUpdate(BaseModel):
    name: str | None = None
    benchmark: str | None = None
    cash: Decimal | None = None
    meta: dict | None = None


class StrategyRequest(BaseModel):
    method: str  # will be validated in handler
    tickers: list[str]
    params: AllocatorParams = AllocatorParams()


class RebalanceRequest(BaseModel):
    strategy_id: str
    params: RebalanceParams = RebalanceParams()


@router.get("")
async def list_portfolios():
    return ok([
        {"portfolio_id": p.portfolio_id, "name": p.name, "benchmark": p.benchmark,
         "cash": str(p.cash), "updated_at": p.updated_at.isoformat(), "created_at": p.created_at.isoformat()}
        for p in storage.list_portfolios()
    ])


@router.post("")
async def create_portfolio(body: PortfolioCreate):
    pid = storage.gen_portfolio_id()
    now = datetime.now()
    p = Portfolio(portfolio_id=pid, name=body.name, benchmark=body.benchmark,
                  cash=body.cash, meta=body.meta, created_at=now, updated_at=now)
    storage.save_portfolio(p)
    return ok({"portfolio_id": pid, "name": p.name, "created_at": p.created_at.isoformat()})


@router.get("/{pid}")
async def get_portfolio(pid: str):
    try:
        p = storage.load_portfolio(pid)
    except storage.PortfolioNotFound:
        raise HTTPException(status_code=404, detail="portfolio not found")
    return ok(p.model_dump(mode="json"))


@router.put("/{pid}")
async def update_portfolio(pid: str, body: PortfolioUpdate):
    try:
        p = storage.load_portfolio(pid)
    except storage.PortfolioNotFound:
        raise HTTPException(status_code=404, detail="portfolio not found")
    if body.name is not None:
        p.name = body.name
    if body.benchmark is not None:
        p.benchmark = body.benchmark
    if body.cash is not None:
        p.cash = body.cash
    if body.meta is not None:
        p.meta = body.meta
    storage.save_portfolio(p)
    return ok(p.model_dump(mode="json"))


@router.delete("/{pid}")
async def delete_portfolio(pid: str):
    try:
        storage.delete_portfolio(pid)
    except storage.PortfolioNotFound:
        raise HTTPException(status_code=404, detail="portfolio not found")
    return ok({"deleted": pid})


# --- CSV Import ---


@router.post("/{pid}/import")
async def import_csv(pid: str, mode: str = Query("merge"), file: UploadFile = File(...)):
    try:
        storage.load_portfolio(pid)
    except storage.PortfolioNotFound:
        raise HTTPException(status_code=404, detail="portfolio not found")
    content = await file.read()
    fmt = detect_format(content)
    if fmt == "eastmoney":
        holdings = parse_eastmoney_csv(content)
    elif fmt == "generic":
        holdings = parse_generic_csv(content)
    else:
        raise HTTPException(status_code=400, detail="unknown CSV format")
    if mode == "replace":
        p = storage.load_portfolio(pid)
        p.holdings = []
        storage.save_portfolio(p)
    for h in holdings:
        storage.add_holding(pid, h)
    return ok({
        "format": fmt, "imported_rows": len(holdings),
        "total_rows": len(holdings), "errors": [],
        "holdings_count": len(storage.load_portfolio(pid).holdings),
    })


# --- Holdings CRUD ---


@router.get("/{pid}/holdings")
async def list_holdings(pid: str):
    try:
        p = storage.load_portfolio(pid)
    except storage.PortfolioNotFound:
        raise HTTPException(status_code=404, detail="portfolio not found")
    return ok([h.model_dump(mode="json") for h in p.holdings])


@router.post("/{pid}/holdings")
async def add_holding(pid: str, body: Holding):
    try:
        storage.load_portfolio(pid)
    except storage.PortfolioNotFound:
        raise HTTPException(status_code=404, detail="portfolio not found")
    if not body.lots:
        body.lots = []
    for lot in body.lots:
        if not lot.lot_id:
            lot.lot_id = storage.gen_lot_id()
    updated = storage.add_holding(pid, body)
    return ok(updated.holdings[-1].model_dump(mode="json"))


@router.put("/{pid}/holdings/{ticker}")
async def update_holding(pid: str, ticker: str, body: Holding):
    try:
        updated = storage.update_holding(pid, ticker, body)
    except storage.PortfolioNotFound:
        raise HTTPException(status_code=404, detail="portfolio not found")
    except storage.HoldingNotFound:
        raise HTTPException(status_code=404, detail="holding not found")
    return ok(updated.model_dump(mode="json"))


@router.delete("/{pid}/holdings/{ticker}")
async def delete_holding(pid: str, ticker: str):
    try:
        storage.remove_holding(pid, ticker)
    except storage.PortfolioNotFound:
        raise HTTPException(status_code=404, detail="portfolio not found")
    except storage.HoldingNotFound:
        raise HTTPException(status_code=404, detail="holding not found")
    return ok({"deleted": ticker})


@router.post("/{pid}/holdings/{ticker}/lots")
async def add_lot(pid: str, ticker: str, body: Lot):
    try:
        p = storage.load_portfolio(pid)
    except storage.PortfolioNotFound:
        raise HTTPException(status_code=404, detail="portfolio not found")
    if not body.lot_id:
        body.lot_id = storage.gen_lot_id()
    for h in p.holdings:
        if h.ticker == ticker:
            h.lots.append(body)
            storage.save_portfolio(p)
            return ok(h.model_dump(mode="json"))
    raise HTTPException(status_code=404, detail="holding not found")


# --- Analytics ---


@router.get("/{pid}/analytics")
async def get_analytics(pid: str, router_obj: DataRouter = Depends(get_data_router)):
    try:
        p = storage.load_portfolio(pid)
    except storage.PortfolioNotFound:
        raise HTTPException(status_code=404, detail="portfolio not found")
    price_lookup = DataRouterPriceLookup(router_obj)
    sector_lookup = DataRouterSectorLookup(router_obj)
    try:
        hist_lookup = DataRouterHistoricalLookup(router_obj)
        result = await compute_analytics(p, price_lookup, sector_lookup=sector_lookup, historical_lookup=hist_lookup)
    except Exception:
        result = await compute_analytics(p, price_lookup)
    return ok(result.model_dump(mode="json"))


# --- Strategies ---


@router.post("/{pid}/strategies")
async def create_strategy(pid: str, body: StrategyRequest, router_obj: DataRouter = Depends(get_data_router)):
    import datetime as _dt
    try:
        storage.load_portfolio(pid)
    except storage.PortfolioNotFound:
        raise HTTPException(status_code=404, detail="portfolio not found")
    price_lookup = DataRouterPriceLookup(router_obj)
    hist_lookup = DataRouterHistoricalLookup(router_obj)
    prices = {t: await price_lookup.get(t, _dt.date.today()) for t in body.tickers}
    result = await allocate(body.method, body.tickers, prices, price_lookup, hist_lookup, body.params)
    strat = Strategy(
        strategy_id=storage.gen_strategy_id(),
        name=f"{body.method}_{datetime.now().strftime('%Y%m%d_%H%M')}",
        method=result.method, target_weights=result.target_weights,
        expected_return=result.expected_return, expected_volatility=result.expected_volatility,
        rationale=result.rationale, created_at=datetime.now(),
        params=body.params.model_dump(),
    )
    storage.add_strategy(pid, strat)
    return ok({**strat.model_dump(mode="json"), "sharpe": result.sharpe, "diagnostics": result.diagnostics})


@router.get("/{pid}/strategies")
async def list_strategies(pid: str):
    try:
        p = storage.load_portfolio(pid)
    except storage.PortfolioNotFound:
        raise HTTPException(status_code=404, detail="portfolio not found")
    return ok([s.model_dump(mode="json") for s in p.strategies])


@router.get("/{pid}/strategies/{sid}")
async def get_strategy(pid: str, sid: str):
    try:
        p = storage.load_portfolio(pid)
    except storage.PortfolioNotFound:
        raise HTTPException(status_code=404, detail="portfolio not found")
    for s in p.strategies:
        if s.strategy_id == sid:
            return ok(s.model_dump(mode="json"))
    raise HTTPException(status_code=404, detail="strategy not found")


@router.delete("/{pid}/strategies/{sid}")
async def delete_strategy(pid: str, sid: str):
    try:
        storage.remove_strategy(pid, sid)
    except storage.PortfolioNotFound:
        raise HTTPException(status_code=404, detail="portfolio not found")
    except storage.StrategyNotFound:
        raise HTTPException(status_code=404, detail="strategy not found")
    return ok({"deleted": sid})


# --- Rebalance ---


@router.post("/{pid}/rebalance")
async def create_rebalance(pid: str, body: RebalanceRequest, router_obj: DataRouter = Depends(get_data_router)):
    try:
        p = storage.load_portfolio(pid)
    except storage.PortfolioNotFound:
        raise HTTPException(status_code=404, detail="portfolio not found")
    target = next((s for s in p.strategies if s.strategy_id == body.strategy_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="strategy not found")
    all_portfolios = storage.list_portfolios()
    price_lookup = DataRouterPriceLookup(router_obj)
    plan = await suggest_rebalance(p, target, all_portfolios, price_lookup, body.params)
    return ok(plan.model_dump(mode="json"))
