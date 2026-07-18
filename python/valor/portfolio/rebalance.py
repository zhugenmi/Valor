"""Rebalance suggester. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel
from valor.portfolio.models import (
    Portfolio, Strategy, RebalanceAction, RebalancePlan, FundTransfer,
)
from valor.portfolio.analytics import compute_analytics, PriceLookup


class RebalanceParams(BaseModel):
    commission_rate: Decimal = Decimal("0.00025")
    min_commission: Decimal = Decimal("5.00")
    stamp_duty_rate: Decimal = Decimal("0.0005")
    transfer_fee_rate: Decimal = Decimal("0.00001")
    min_lot_size: int = 100
    allow_partial_lot: bool = False
    transfer_threshold: Decimal = Decimal("1000")


def _estimate_trade_cost(ticker: str, side: str, quantity: int, price: Decimal, params: RebalanceParams) -> Decimal:
    notional = Decimal(quantity) * price
    commission = max(notional * params.commission_rate, params.min_commission)
    stamp_duty = notional * params.stamp_duty_rate if side == "sell" else Decimal("0")
    is_sh = ticker.startswith(("60", "68"))
    transfer_fee = notional * params.transfer_fee_rate if is_sh else Decimal("0")
    return commission + stamp_duty + transfer_fee


def _round_to_lot(qty: int, lot_size: int, allow_partial: bool) -> int:
    if allow_partial:
        return qty
    return (qty // lot_size) * lot_size


async def suggest_rebalance(
    portfolio: Portfolio,
    target_strategy: Strategy,
    all_portfolios: list[Portfolio],
    price_lookup: PriceLookup,
    params: RebalanceParams,
) -> RebalancePlan:
    analytics = await compute_analytics(portfolio, price_lookup)
    total_value = analytics.total_market_value + portfolio.cash
    current_map = {p.ticker: p for p in analytics.positions}
    current_qty_map = {
        h.ticker: sum(lot.quantity for lot in h.lots) for h in portfolio.holdings
    }
    actions: list[RebalanceAction] = []
    all_tickers = set(target_strategy.target_weights.keys()) | set(current_qty_map.keys())
    for ticker in all_tickers:
        target_w = target_strategy.target_weights.get(ticker, 0.0)
        price = await price_lookup.get(ticker, analytics.as_of)
        target_value = total_value * Decimal(str(target_w))
        raw_qty = int(target_value / price) if price > 0 else 0
        target_qty = _round_to_lot(raw_qty, params.min_lot_size, params.allow_partial_lot)
        current_qty = current_qty_map.get(ticker, 0)
        delta = target_qty - current_qty
        if delta == 0:
            continue
        side = "buy" if delta > 0 else "sell"
        current_w = current_map[ticker].weight if ticker in current_map else 0.0
        est_cost = _estimate_trade_cost(ticker, side, abs(delta), price, params)
        actions.append(RebalanceAction(
            ticker=ticker, side=side, target_quantity=target_qty,
            delta_quantity=delta, target_weight=target_w, current_weight=current_w,
            est_cost=est_cost,
            rationale=f"目标权重 {target_w:.1%}，当前 {current_w:.1%}，{side} {abs(delta)} 股",
        ))
    total_cost = sum((a.est_cost for a in actions), Decimal("0"))
    buy_total = Decimal("0")
    for a in actions:
        if a.side == "buy":
            buy_total += Decimal(abs(a.delta_quantity)) * (await price_lookup.get(a.ticker, analytics.as_of))
    sell_total = Decimal("0")
    for a in actions:
        if a.side == "sell":
            sell_total += Decimal(abs(a.delta_quantity)) * (await price_lookup.get(a.ticker, analytics.as_of))
    net_needed = buy_total - sell_total + total_cost
    cash_after = portfolio.cash - net_needed
    fund_transfers: list[FundTransfer] = []
    warnings: list[str] = []
    if cash_after < 0:
        deficit = -cash_after
        others = sorted(
            [p for p in all_portfolios if p.portfolio_id != portfolio.portfolio_id and p.cash > params.transfer_threshold],
            key=lambda p: -p.cash,
        )
        remaining = deficit
        for op in others:
            if remaining <= 0:
                break
            transfer = min(op.cash, remaining)
            if transfer >= params.transfer_threshold:
                fund_transfers.append(FundTransfer(
                    from_portfolio_id=op.portfolio_id,
                    to_portfolio_id=portfolio.portfolio_id,
                    amount=transfer,
                    rationale=f"调仓资金缺口 {deficit:.2f}，从 {op.name} 调拨 {transfer:.2f}",
                ))
                remaining -= transfer
                cash_after += transfer
        if cash_after < 0:
            warnings.append(f"资金缺口 {Decimal('-1') * cash_after:.2f} 无法完全补足")
    if not actions:
        warnings.append("当前组合已符合目标")
    return RebalancePlan(
        portfolio_id=portfolio.portfolio_id, strategy_id=target_strategy.strategy_id,
        actions=actions, total_est_cost=total_cost,
        cash_before=portfolio.cash, cash_after=cash_after,
        fund_transfers=fund_transfers, warnings=warnings,
        created_at=datetime.now(),
    )
