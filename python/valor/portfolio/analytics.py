"""Portfolio analytics. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Protocol
import numpy as np
from pydantic import BaseModel
from valor.portfolio.models import Portfolio


class PriceLookup(Protocol):
    async def get(self, ticker: str, as_of: date) -> Decimal: ...


class SectorLookup(Protocol):
    async def get(self, ticker: str) -> str | None: ...


class HistoricalLookup(Protocol):
    async def get_returns(self, ticker: str, days: int) -> np.ndarray: ...


class PositionMetric(BaseModel):
    ticker: str
    name: str | None
    quantity: int
    cost_price: Decimal
    current_price: Decimal
    market_value: Decimal
    cost_value: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: float
    weight: float
    sector: str | None = None
    beta: float | None = None
    realized_pnl: Decimal = Decimal("0")


class ConcentrationMetrics(BaseModel):
    top1_weight: float
    top5_weight: float
    herfindahl_index: float
    num_holdings: int
    effective_holdings: float


class PortfolioAnalytics(BaseModel):
    portfolio_id: str
    as_of: date
    total_market_value: Decimal
    total_cost_value: Decimal
    cash: Decimal
    total_assets: Decimal
    total_unrealized_pnl: Decimal
    total_unrealized_pnl_pct: float
    positions: list[PositionMetric]
    sector_exposure: dict[str, float] = {}
    concentration: ConcentrationMetrics
    benchmark: str | None = None
    portfolio_beta: float | None = None


async def compute_analytics(
    portfolio: Portfolio,
    price_lookup: PriceLookup,
    benchmark_lookup: object | None = None,
    as_of: date | None = None,
    sector_lookup: SectorLookup | None = None,
    historical_lookup: HistoricalLookup | None = None,
) -> PortfolioAnalytics:
    as_of = as_of or date.today()
    positions: list[PositionMetric] = []
    for h in portfolio.holdings:
        qty = sum(lot.quantity for lot in h.lots)
        if qty == 0:
            continue
        cost_value = sum(lot.quantity * lot.cost_price for lot in h.lots) + sum(lot.fees for lot in h.lots)
        avg_cost = cost_value / Decimal(qty) if qty else Decimal("0")
        price = await price_lookup.get(h.ticker, as_of)
        market_value = Decimal(qty) * price
        pnl = market_value - cost_value
        positions.append(PositionMetric(
            ticker=h.ticker, name=h.name, quantity=qty, cost_price=avg_cost,
            current_price=price, market_value=market_value, cost_value=cost_value,
            unrealized_pnl=pnl,
            unrealized_pnl_pct=float(pnl / cost_value) if cost_value else 0.0,
            weight=0.0,
        ))
    total_mv = sum((p.market_value for p in positions), Decimal("0"))
    total_cost = sum((p.cost_value for p in positions), Decimal("0"))
    for p in positions:
        p.weight = float(p.market_value / total_mv) if total_mv else 0.0
    sorted_w = sorted([p.weight for p in positions], reverse=True)
    hhi = sum(w * w for w in sorted_w)
    top1 = sorted_w[0] if sorted_w else 0.0
    top5 = sum(sorted_w[:5])
    eff = 1.0 / hhi if hhi > 0 else 0.0
    total_pnl = total_mv - total_cost
    concentration = ConcentrationMetrics(
        top1_weight=top1, top5_weight=top5, herfindahl_index=hhi,
        num_holdings=len(positions), effective_holdings=eff,
    )
    sector_exposure: dict[str, float] = {}
    if sector_lookup:
        for p in positions:
            sec = await sector_lookup.get(p.ticker)
            if sec:
                p.sector = sec
                sector_exposure[sec] = sector_exposure.get(sec, 0.0) + p.weight
        unknown_w = sum(p.weight for p in positions if p.sector is None)
        if unknown_w > 0:
            sector_exposure["未知"] = unknown_w

    portfolio_beta: float | None = None
    if historical_lookup and portfolio.benchmark:
        bench_ret = await historical_lookup.get_returns(portfolio.benchmark, 252)
        betas: list[tuple[float, float]] = []
        for p in positions:
            rets = await historical_lookup.get_returns(p.ticker, 252)
            if len(rets) < 30 or len(bench_ret) < 30:
                continue
            cov = np.cov(rets[-252:], bench_ret[-252:])[0, 1]
            var = np.var(bench_ret[-252:])
            beta = float(cov / var) if var > 0 else 1.0
            p.beta = beta
            betas.append((p.weight, beta))
        if betas:
            portfolio_beta = sum(w * b for w, b in betas)

    return PortfolioAnalytics(
        portfolio_id=portfolio.portfolio_id, as_of=as_of,
        total_market_value=total_mv, total_cost_value=total_cost,
        cash=portfolio.cash, total_assets=total_mv + portfolio.cash,
        total_unrealized_pnl=total_pnl,
        total_unrealized_pnl_pct=float(total_pnl / total_cost) if total_cost else 0.0,
        positions=positions, concentration=concentration,
        sector_exposure=sector_exposure,
        benchmark=portfolio.benchmark, portfolio_beta=portfolio_beta,
    )
