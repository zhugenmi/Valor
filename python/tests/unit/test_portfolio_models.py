"""Tests for portfolio models and default portfolio lookup in stream.py.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

from valor.portfolio.models import (
    Holding, Lot, Portfolio, RebalanceAction, RebalancePlan, SellLot, Strategy,
)
from valor.server.routes.stream import _load_default_portfolio


def test_lot_defaults():
    lot = Lot(lot_id="l1", open_date=date(2024, 1, 1), quantity=100, cost_price=Decimal("10.5"))
    assert lot.fees == Decimal("0")
    assert lot.note is None


def test_holding_default_side():
    h = Holding(ticker="600519")
    assert h.side == "long"
    assert h.lots == []


def test_strategy_method_literal():
    with pytest.raises(ValueError):
        Strategy(strategy_id="s1", name="x", method="black_litterman",
                 target_weights={}, rationale="", created_at=datetime.now())


def test_portfolio_defaults():
    p = Portfolio(portfolio_id="p1", name="main", created_at=datetime.now(), updated_at=datetime.now())
    assert p.benchmark == "000300"
    assert p.cash == Decimal("0")
    assert p.holdings == []
    assert p.strategies == []


def test_rebalance_action_signs():
    a = RebalanceAction(ticker="600519", side="buy", target_quantity=200,
                        delta_quantity=100, target_weight=0.35, current_weight=0.20,
                        est_cost=Decimal("12.50"), rationale="buy")
    assert a.delta_quantity > 0


def test_rebalance_plan_optional_fields():
    plan = RebalancePlan(portfolio_id="p1", strategy_id="s1", actions=[],
                         total_est_cost=Decimal("0"), cash_before=Decimal("1000"),
                         cash_after=Decimal("1000"), created_at=datetime.now())
    assert plan.fund_transfers == []
    assert plan.warnings == []


def test_decimal_serialization():
    p = Portfolio(portfolio_id="p1", name="main", cash=Decimal("50000.00"),
                  created_at=datetime.now(), updated_at=datetime.now())
    js = p.model_dump_json()
    assert "50000.00" in js


# --- SellLot ---


def test_sell_lot_creation():
    s = SellLot(
        sell_id="sell_abc",
        sell_date=date(2026, 7, 19),
        quantity=100,
        sell_price=Decimal("1820.00"),
        fees=Decimal("15.50"),
        realized_pnl=Decimal("12984.50"),
        avg_cost_at_sell=Decimal("1689.50"),
    )
    assert s.sell_id == "sell_abc"
    assert s.quantity == 100
    assert s.realized_pnl == Decimal("12984.50")


def test_holding_has_sell_lots_default_empty():
    h = Holding(ticker="600519", lots=[])
    assert h.sell_lots == []


def test_holding_with_sell_lots():
    h = Holding(
        ticker="600519",
        lots=[Lot(lot_id="l1", open_date=date(2024, 1, 1), quantity=100, cost_price=Decimal("1689.50"))],
        sell_lots=[SellLot(
            sell_id="s1", sell_date=date(2026, 7, 19), quantity=50,
            sell_price=Decimal("1820.00"), fees=Decimal("5.00"),
            realized_pnl=Decimal("6500.00"), avg_cost_at_sell=Decimal("1689.50"),
        )],
    )
    assert len(h.sell_lots) == 1
    assert h.sell_lots[0].sell_id == "s1"


def test_position_metric_has_realized_pnl_default_zero():
    from valor.portfolio.analytics import PositionMetric
    pm = PositionMetric(
        ticker="600519", name="贵州茅台", quantity=100,
        cost_price=Decimal("1689.50"), current_price=Decimal("1800.00"),
        market_value=Decimal("180000.00"), cost_value=Decimal("168950.00"),
        unrealized_pnl=Decimal("11050.00"), unrealized_pnl_pct=0.065, weight=1.0,
    )
    assert pm.realized_pnl == Decimal("0")


# --- default portfolio lookup (stream.py) ---


def _make_lot(qty: int) -> Lot:
    return Lot(
        lot_id=f"lot_{qty}",
        open_date=date(2026, 7, 19),
        quantity=qty,
        cost_price=Decimal("6.00"),
    )


def _make_portfolio(name: str, pf_id: str, cash: str, holdings: list[Holding]) -> Portfolio:
    now = datetime(2026, 7, 19, 12, 0, 0)
    return Portfolio(
        portfolio_id=pf_id,
        name=name,
        cash=Decimal(cash),
        holdings=holdings,
        created_at=now,
        updated_at=now,
    )


def test_load_default_portfolio_finds_chicang_with_matching_ticker():
    """'持仓' 组合含 601728 持仓 5000 股 -> 返回 cash=0, stock=5000, id=pf_xxx。"""
    pf_holdings = _make_portfolio(
        "持仓", "pf_1932b2a5", "0",
        [Holding(ticker="601728", name="中国电信", lots=[_make_lot(5000)])],
    )
    pf_other = _make_portfolio("策略A", "pf_aaa", "50000", [])
    with patch(
        "valor.portfolio.storage.list_portfolios",
        return_value=[pf_other, pf_holdings],
    ):
        portfolio, pf_id = _load_default_portfolio("601728")
    assert portfolio == {"cash": 0.0, "stock": 5000}
    assert pf_id == "pf_1932b2a5"


def test_load_default_portfolio_ticker_not_held():
    """'持仓' 组合存在但不含 600519 -> stock=0, cash 取自组合。"""
    pf_holdings = _make_portfolio(
        "持仓", "pf_1932b2a5", "10000",
        [Holding(ticker="601728", name="中国电信", lots=[_make_lot(5000)])],
    )
    with patch(
        "valor.portfolio.storage.list_portfolios",
        return_value=[pf_holdings],
    ):
        portfolio, pf_id = _load_default_portfolio("600519")
    assert portfolio == {"cash": 10000.0, "stock": 0}
    assert pf_id == "pf_1932b2a5"


def test_load_default_portfolio_no_chicang_falls_back():
    """没有名字为'持仓'的组合 -> 返回默认 {cash:100000, stock:0}, id=None。"""
    pf_other = _make_portfolio("策略A", "pf_aaa", "50000", [])
    with patch(
        "valor.portfolio.storage.list_portfolios",
        return_value=[pf_other],
    ):
        portfolio, pf_id = _load_default_portfolio("601728")
    assert portfolio == {"cash": 100000.0, "stock": 0}
    assert pf_id is None


def test_load_default_portfolio_list_error_falls_back():
    """list_portfolios 抛异常 -> 返回默认兜底。"""
    with patch(
        "valor.portfolio.storage.list_portfolios",
        side_effect=RuntimeError("disk error"),
    ):
        portfolio, pf_id = _load_default_portfolio("601728")
    assert portfolio == {"cash": 100000.0, "stock": 0}
    assert pf_id is None


def test_load_default_portfolio_multiple_lots_summed():
    """同一 ticker 多个 lot -> stock 数量求和。"""
    pf_holdings = _make_portfolio(
        "持仓", "pf_x", "1000",
        [Holding(
            ticker="601728", name="中国电信",
            lots=[_make_lot(5000), _make_lot(3000)],
        )],
    )
    with patch(
        "valor.portfolio.storage.list_portfolios",
        return_value=[pf_holdings],
    ):
        portfolio, _ = _load_default_portfolio("601728")
    assert portfolio["stock"] == 8000