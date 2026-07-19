from datetime import date, datetime
from decimal import Decimal
import pytest
from valor.portfolio.models import (
    Lot, Holding, SellLot, Strategy, Portfolio, RebalanceAction, RebalancePlan,
)


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
