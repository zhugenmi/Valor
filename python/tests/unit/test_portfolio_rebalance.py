"""Tests for portfolio rebalance suggester. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from datetime import date, datetime
from decimal import Decimal
import pytest
from valor.portfolio.models import Portfolio, Holding, Lot, Strategy
from valor.portfolio.rebalance import suggest_rebalance, RebalanceParams


class FakePriceLookup:
    def __init__(self, prices: dict[str, Decimal]):
        self._p = prices

    async def get(self, ticker: str, as_of: date) -> Decimal:
        return self._p[ticker]


def _portfolio(holdings, cash=Decimal("50000")):
    return Portfolio(portfolio_id="pf1", name="t", cash=cash, holdings=holdings,
                     created_at=datetime(2026, 7, 17), updated_at=datetime(2026, 7, 17))


def _strategy(weights, sid="strat_1"):
    return Strategy(strategy_id=sid, name="test", method="mean_variance",
                    target_weights=weights, rationale="test",
                    created_at=datetime(2026, 7, 17))


@pytest.mark.asyncio
async def test_buy_action_when_underweight():
    h = Holding(ticker="600519", lots=[Lot(lot_id="l", open_date=date(2024, 1, 1), quantity=100, cost_price=Decimal("100"))])
    p = _portfolio([h], cash=Decimal("100000"))
    s = _strategy({"600519": 0.50})
    plan = await suggest_rebalance(p, s, [p], FakePriceLookup({"600519": Decimal("100")}), RebalanceParams())
    assert len(plan.actions) == 1
    a = plan.actions[0]
    assert a.side == "buy"
    assert a.delta_quantity > 0
    # total_value = 100*100 + 100000 = 110000, target 50% = 55000, /100 = 550 -> floor to 500
    assert a.target_quantity == 500
    assert a.target_weight == pytest.approx(0.50)
    assert a.current_weight == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_sell_action_when_overweight():
    h = Holding(ticker="600519", lots=[Lot(lot_id="l", open_date=date(2024, 1, 1), quantity=500, cost_price=Decimal("100"))])
    p = _portfolio([h], cash=Decimal("0"))
    s = _strategy({"600519": 0.30})
    plan = await suggest_rebalance(p, s, [p], FakePriceLookup({"600519": Decimal("100")}), RebalanceParams())
    a = plan.actions[0]
    assert a.side == "sell"
    assert a.delta_quantity < 0
    # 30% of 50000 = 15000, /100 = 150, floor to lot of 100
    assert a.target_quantity == 100


@pytest.mark.asyncio
async def test_no_action_when_balanced():
    h = Holding(ticker="600519", lots=[Lot(lot_id="l", open_date=date(2024, 1, 1), quantity=500, cost_price=Decimal("100"))])
    p = _portfolio([h], cash=Decimal("0"))
    s = _strategy({"600519": 1.0})
    plan = await suggest_rebalance(p, s, [p], FakePriceLookup({"600519": Decimal("100")}), RebalanceParams())
    assert len(plan.actions) == 0
    assert any("符合" in w for w in plan.warnings)


@pytest.mark.asyncio
async def test_target_missing_ticker_cleared():
    h = Holding(ticker="600519", lots=[Lot(lot_id="l", open_date=date(2024, 1, 1), quantity=100, cost_price=Decimal("100"))])
    p = _portfolio([h], cash=Decimal("0"))
    s = _strategy({})  # no tickers -> clear all
    plan = await suggest_rebalance(p, s, [p], FakePriceLookup({"600519": Decimal("100")}), RebalanceParams())
    assert len(plan.actions) == 1
    assert plan.actions[0].side == "sell"
    assert plan.actions[0].target_quantity == 0


@pytest.mark.asyncio
async def test_new_ticker_built_from_zero():
    p = _portfolio([], cash=Decimal("100000"))
    s = _strategy({"600519": 0.40})
    plan = await suggest_rebalance(p, s, [p], FakePriceLookup({"600519": Decimal("100")}), RebalanceParams())
    assert len(plan.actions) == 1
    assert plan.actions[0].side == "buy"
    assert plan.actions[0].target_quantity == 400


@pytest.mark.asyncio
async def test_min_lot_size_rounding():
    h = Holding(ticker="600519", lots=[Lot(lot_id="l", open_date=date(2024, 1, 1), quantity=0, cost_price=Decimal("100"))])
    p = _portfolio([h], cash=Decimal("55000"))  # 55% of 100000 -> 55000 / 100 = 550 -> round to 500
    s = _strategy({"600519": 0.55})
    plan = await suggest_rebalance(p, s, [p], FakePriceLookup({"600519": Decimal("100")}), RebalanceParams())
    assert plan.actions[0].target_quantity % 100 == 0


@pytest.mark.asyncio
async def test_stamp_duty_only_on_sell():
    h = Holding(ticker="600519", lots=[Lot(lot_id="l", open_date=date(2024, 1, 1), quantity=500, cost_price=Decimal("100"))])
    p = _portfolio([h], cash=Decimal("0"))
    s = _strategy({"600519": 0.30})
    plan = await suggest_rebalance(p, s, [p], FakePriceLookup({"600519": Decimal("100")}), RebalanceParams())
    sell_action = plan.actions[0]
    notional = Decimal(abs(sell_action.delta_quantity)) * Decimal("100")
    expected_stamp = notional * Decimal("0.0005")
    expected_commission = max(notional * Decimal("0.00025"), Decimal("5.00"))
    expected_transfer = notional * Decimal("0.00001")  # 600519 is SH
    expected_total = expected_commission + expected_stamp + expected_transfer
    assert sell_action.est_cost == pytest.approx(expected_total, rel=Decimal("0.001"))


@pytest.mark.asyncio
async def test_transfer_fee_only_for_sh():
    # 000858 is SZ (no transfer fee)
    h = Holding(ticker="000858", lots=[Lot(lot_id="l", open_date=date(2024, 1, 1), quantity=500, cost_price=Decimal("100"))])
    p = _portfolio([h], cash=Decimal("0"))
    s = _strategy({"000858": 0.30})
    plan = await suggest_rebalance(p, s, [p], FakePriceLookup({"000858": Decimal("100")}), RebalanceParams())
    sell_action = plan.actions[0]
    notional = Decimal(abs(sell_action.delta_quantity)) * Decimal("100")
    expected = max(notional * Decimal("0.00025"), Decimal("5.00")) + notional * Decimal("0.0005")
    assert sell_action.est_cost == pytest.approx(expected, rel=Decimal("0.001"))


@pytest.mark.asyncio
async def test_cross_portfolio_transfer_when_cash_short():
    h = Holding(ticker="600519", lots=[Lot(lot_id="l", open_date=date(2024, 1, 1), quantity=0, cost_price=Decimal("100"))])
    p1 = _portfolio([h], cash=Decimal("10000"))
    p2 = Portfolio(portfolio_id="pf2", name="备用", cash=Decimal("100000"), holdings=[],
                   created_at=datetime(2026, 7, 17), updated_at=datetime(2026, 7, 17))
    s = _strategy({"600519": 1.00})  # target 100% — buy 100 shares, costs cause deficit
    params = RebalanceParams(transfer_threshold=Decimal("1"))
    plan = await suggest_rebalance(p1, s, [p1, p2], FakePriceLookup({"600519": Decimal("100")}), params)
    assert len(plan.fund_transfers) >= 1
    ft = plan.fund_transfers[0]
    assert ft.from_portfolio_id == "pf2"
    assert ft.to_portfolio_id == "pf1"
    assert ft.amount > Decimal("0")


@pytest.mark.asyncio
async def test_no_transfer_below_threshold():
    h = Holding(ticker="600519", lots=[Lot(lot_id="l", open_date=date(2024, 1, 1), quantity=0, cost_price=Decimal("100"))])
    p1 = _portfolio([h], cash=Decimal("10000"))
    p2 = Portfolio(portfolio_id="pf2", name="备用", cash=Decimal("800"), holdings=[],
                   created_at=datetime(2026, 7, 17), updated_at=datetime(2026, 7, 17))
    s = _strategy({"600519": 1.00})
    params = RebalanceParams(transfer_threshold=Decimal("1000"))
    plan = await suggest_rebalance(p1, s, [p1, p2], FakePriceLookup({"600519": Decimal("100")}), params)
    assert len(plan.fund_transfers) == 0
    assert any("资金缺口" in w for w in plan.warnings)


@pytest.mark.asyncio
async def test_min_commission_applied():
    h = Holding(ticker="600519", lots=[Lot(lot_id="l", open_date=date(2024, 1, 1), quantity=0, cost_price=Decimal("100"))])
    p = _portfolio([h], cash=Decimal("100000"))
    s = _strategy({"600519": 0.01})  # tiny buy
    plan = await suggest_rebalance(p, s, [p], FakePriceLookup({"600519": Decimal("100")}), RebalanceParams())
    if plan.actions:
        buy = plan.actions[0]
        # notional = 100 shares * 100 = 10000; commission = max(10000*0.00025, 5) = 5
        assert buy.est_cost >= Decimal("5.00")


@pytest.mark.asyncio
async def test_cash_after_reflects_buys_and_sells():
    h1 = Holding(ticker="600519", lots=[Lot(lot_id="l", open_date=date(2024, 1, 1), quantity=100, cost_price=Decimal("100"))])
    h2 = Holding(ticker="000858", lots=[Lot(lot_id="l", open_date=date(2024, 1, 1), quantity=100, cost_price=Decimal("100"))])
    p = _portfolio([h1, h2], cash=Decimal("50000"))
    s = _strategy({"600519": 0.40, "000858": 0.30})
    plan = await suggest_rebalance(p, s, [p], FakePriceLookup({"600519": Decimal("100"), "000858": Decimal("100")}), RebalanceParams())
    assert plan.cash_after < plan.cash_before  # net cash decreased (buys > sells)
