from datetime import date, datetime
from decimal import Decimal
import pytest
from valor.portfolio.models import (
    Lot, Holding, Strategy, Portfolio, RebalanceAction, RebalancePlan,
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
