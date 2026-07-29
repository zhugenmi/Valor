"""Portfolio analytics. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations
import asyncio
from datetime import date
from decimal import Decimal
from typing import Protocol
import numpy as np
from pydantic import BaseModel
from valor.portfolio.models import Portfolio
from valor.utils.logging_config import setup_logger

logger = setup_logger("portfolio.analytics")

# Concurrency limits to avoid overwhelming upstream data sources (AkShare etc.).
# Realtime quotes are light and already fail-fast via _spot_proxy (max_attempts=1);
# financial indicators and daily history are heavier, so use a tighter cap.
_PRICE_SEMAPHORE = asyncio.Semaphore(10)
_SECTOR_SEMAPHORE = asyncio.Semaphore(5)
_HISTORY_SEMAPHORE = asyncio.Semaphore(5)


class PriceLookup(Protocol):
    async def get(self, ticker: str, as_of: date) -> Decimal: ...


class SectorLookup(Protocol):
    async def get(self, ticker: str) -> str | None: ...


class HistoricalLookup(Protocol):
    async def get_returns(self, ticker: str, days: int) -> np.ndarray: ...


async def _safe_price_get(lookup: PriceLookup, ticker: str, as_of: date) -> Decimal | None:
    async with _PRICE_SEMAPHORE:
        try:
            return await lookup.get(ticker, as_of)
        except Exception as exc:  # noqa: BLE001
            logger.warning("price lookup failed for %s: %s", ticker, exc)
            return None


async def _safe_sector_get(lookup: SectorLookup, ticker: str) -> str | None:
    async with _SECTOR_SEMAPHORE:
        try:
            return await lookup.get(ticker)
        except Exception as exc:  # noqa: BLE001
            logger.warning("sector lookup failed for %s: %s", ticker, exc)
            return None


async def _safe_returns_get(lookup: HistoricalLookup, ticker: str, days: int) -> np.ndarray:
    async with _HISTORY_SEMAPHORE:
        try:
            return await lookup.get_returns(ticker, days)
        except Exception as exc:  # noqa: BLE001
            logger.warning("returns lookup failed for %s: %s", ticker, exc)
            return np.array([])


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

    # Phase 1: pre-compute static fields per holding (no I/O).
    # Tuple = (holding, qty, cost_value, avg_cost, realized_pnl).
    static: list[tuple[object, int, Decimal, Decimal, Decimal]] = []
    for h in portfolio.holdings:
        qty = sum(lot.quantity for lot in h.lots)
        if qty == 0:
            continue
        cost_value = sum(lot.quantity * lot.cost_price for lot in h.lots) + sum(lot.fees for lot in h.lots)
        avg_cost = cost_value / Decimal(qty) if qty else Decimal("0")
        realized = sum((s.realized_pnl for s in h.sell_lots), Decimal("0"))
        static.append((h, qty, cost_value, avg_cost, realized))

    # Phase 2: fetch all prices in parallel. Failed lookups return None and the
    # corresponding holding is skipped (logged via _safe_price_get).
    prices = await asyncio.gather(
        *[_safe_price_get(price_lookup, h.ticker, as_of) for h, *_ in static]
    )

    positions: list[PositionMetric] = []
    for (h, qty, cost_value, avg_cost, realized), price in zip(static, prices, strict=True):
        if price is None:
            continue
        market_value = Decimal(qty) * price
        pnl = market_value - cost_value
        positions.append(PositionMetric(
            ticker=h.ticker, name=h.name, quantity=qty, cost_price=avg_cost,
            current_price=price, market_value=market_value, cost_value=cost_value,
            unrealized_pnl=pnl,
            unrealized_pnl_pct=float(pnl / cost_value) if cost_value else 0.0,
            weight=0.0,
            realized_pnl=realized,
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

    # Phase 3: sector exposure in parallel (tolerant of per-ticker failures).
    sector_exposure: dict[str, float] = {}
    if sector_lookup and positions:
        sectors = await asyncio.gather(
            *[_safe_sector_get(sector_lookup, p.ticker) for p in positions]
        )
        for p, sec in zip(positions, sectors, strict=True):
            if sec:
                p.sector = sec
                sector_exposure[sec] = sector_exposure.get(sec, 0.0) + p.weight
        unknown_w = sum(p.weight for p in positions if p.sector is None)
        if unknown_w > 0:
            sector_exposure["未知"] = unknown_w

    # Phase 4: portfolio beta - fetch benchmark + all position returns in parallel.
    portfolio_beta: float | None = None
    if historical_lookup and portfolio.benchmark and positions:
        bench_ret = await _safe_returns_get(historical_lookup, portfolio.benchmark, 252)
        if len(bench_ret) >= 30:
            rets_list = await asyncio.gather(
                *[_safe_returns_get(historical_lookup, p.ticker, 252) for p in positions]
            )
            betas: list[tuple[float, float]] = []
            for p, rets in zip(positions, rets_list, strict=True):
                if len(rets) < 30:
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
