"""Portfolio domain models. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel


class Lot(BaseModel):
    lot_id: str
    open_date: date
    quantity: int
    cost_price: Decimal
    fees: Decimal = Decimal("0")
    note: str | None = None


class SellLot(BaseModel):
    """单笔卖出记录（用于已实现盈亏追踪）"""
    sell_id: str
    sell_date: date
    quantity: int
    sell_price: Decimal
    fees: Decimal = Decimal("0")
    realized_pnl: Decimal
    avg_cost_at_sell: Decimal
    note: str | None = None


class Holding(BaseModel):
    """单一股票持仓 = 多个 Lot 的聚合"""
    ticker: str
    name: str | None = None
    lots: list[Lot] = []
    sell_lots: list[SellLot] = []
    side: Literal["long", "short"] = "long"


class Strategy(BaseModel):
    strategy_id: str
    name: str
    method: Literal["equal_weight", "mean_variance", "risk_parity"]
    target_weights: dict[str, float]
    expected_return: float | None = None
    expected_volatility: float | None = None
    rationale: str
    created_at: datetime
    params: dict = {}


class Portfolio(BaseModel):
    portfolio_id: str
    name: str
    benchmark: str = "000300"
    cash: Decimal = Decimal("0")
    holdings: list[Holding] = []
    strategies: list[Strategy] = []
    created_at: datetime
    updated_at: datetime
    meta: dict = {}


class FundTransfer(BaseModel):
    from_portfolio_id: str
    to_portfolio_id: str
    amount: Decimal
    rationale: str


class RebalanceAction(BaseModel):
    ticker: str
    side: Literal["buy", "sell"]
    target_quantity: int
    delta_quantity: int
    target_weight: float
    current_weight: float
    est_cost: Decimal
    rationale: str


class RebalancePlan(BaseModel):
    portfolio_id: str
    strategy_id: str
    actions: list[RebalanceAction]
    total_est_cost: Decimal
    cash_before: Decimal
    cash_after: Decimal
    fund_transfers: list[FundTransfer] = []
    warnings: list[str] = []
    created_at: datetime
