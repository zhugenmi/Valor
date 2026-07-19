"""Tests for sell-lot storage operations. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from datetime import date, datetime
from decimal import Decimal
import pytest
from valor.portfolio.models import Holding, Lot, Portfolio, SellLot
from valor.portfolio.storage import (
    DATA_DIR, add_holding, add_sell, deduct_lots_weighted, gen_sell_id,
    save_portfolio, set_data_dir, HoldingNotFound,
)


@pytest.fixture
def tmp_dir(tmp_path, monkeypatch):
    set_data_dir(tmp_path)
    yield tmp_path
    set_data_dir(DATA_DIR)


def test_gen_sell_id_prefix():
    sid = gen_sell_id()
    assert sid.startswith("sell_")


def _lot(lid: str, qty: int, cost: str = "1689.50") -> Lot:
    return Lot(lot_id=lid, open_date=date(2024, 1, 1), quantity=qty, cost_price=Decimal(cost))


def test_deduct_single_lot_partial():
    lot = _lot("l1", 100)
    alloc = deduct_lots_weighted([lot], 30)
    assert alloc == [(lot, 30)]
    assert lot.quantity == 70


def test_deduct_single_lot_full():
    lot = _lot("l1", 100)
    alloc = deduct_lots_weighted([lot], 100)
    assert alloc == [(lot, 100)]
    assert lot.quantity == 0


def test_deduct_multi_lots_proportional():
    l1 = _lot("l1", 100)
    l2 = _lot("l2", 100)
    alloc = deduct_lots_weighted([l1, l2], 50)
    deducted = {lot.lot_id: d for lot, d in alloc}
    assert deducted["l1"] == 25
    assert deducted["l2"] == 25
    assert l1.quantity == 75
    assert l2.quantity == 75


def test_deduct_hamilton_remainder_distribution():
    l1 = _lot("l1", 100)
    l2 = _lot("l2", 100)
    l3 = _lot("l3", 100)
    alloc = deduct_lots_weighted([l1, l2, l3], 10)
    deducted = {lot.lot_id: d for lot, d in alloc}
    total = sum(deducted.values())
    assert total == 10
    assert deducted["l1"] == 4
    assert deducted["l2"] == 3
    assert deducted["l3"] == 3


def test_deduct_exceeds_total_raises():
    lot = _lot("l1", 100)
    with pytest.raises(ValueError, match="exceeds"):
        deduct_lots_weighted([lot], 150)


def test_deduct_zero_or_negative_raises():
    lot = _lot("l1", 100)
    with pytest.raises(ValueError, match="positive"):
        deduct_lots_weighted([lot], 0)
    with pytest.raises(ValueError, match="positive"):
        deduct_lots_weighted([lot], -10)


def test_deduct_cost_price_unchanged():
    lot = _lot("l1", 100, "1689.50")
    deduct_lots_weighted([lot], 30)
    assert lot.cost_price == Decimal("1689.50")


def _seed_portfolio(pid: str = "pf_t") -> Portfolio:
    p = Portfolio(
        portfolio_id=pid, name="t",
        created_at=datetime(2026, 7, 17), updated_at=datetime(2026, 7, 17),
    )
    save_portfolio(p)
    return p


def _seed_holding(pid: str, ticker: str, lots: list[Lot], name: str = "贵州茅台") -> None:
    add_holding(pid, Holding(ticker=ticker, name=name, lots=lots))


def test_add_sell_basic():
    _seed_portfolio()
    _seed_holding("pf_t", "600519", [_lot("l1", 100, "1689.50")])
    sell = SellLot(
        sell_id="", sell_date=date(2026, 7, 19), quantity=30,
        sell_price=Decimal("1820.00"), fees=Decimal("15.00"),
        realized_pnl=Decimal("0"), avg_cost_at_sell=Decimal("0"),
    )
    updated = add_sell("pf_t", "600519", sell)
    h = updated.holdings[0]
    assert len(h.sell_lots) == 1
    assert h.sell_lots[0].quantity == 30
    assert h.lots[0].quantity == 70
    assert h.lots[0].cost_price == Decimal("1689.50")
    assert h.sell_lots[0].sell_id.startswith("sell_")
    assert h.sell_lots[0].avg_cost_at_sell == Decimal("1689.50")
    assert h.sell_lots[0].realized_pnl == Decimal("3900.00")


def test_add_sell_multi_lot_weighted_avg():
    _seed_portfolio()
    _seed_holding("pf_t", "600519", [
        _lot("l1", 100, "1689.50"),
        _lot("l2", 100, "1800.00"),
    ])
    sell = SellLot(
        sell_id="", sell_date=date(2026, 7, 19), quantity=100,
        sell_price=Decimal("1900.00"), fees=Decimal("20.00"),
        realized_pnl=Decimal("0"), avg_cost_at_sell=Decimal("0"),
    )
    updated = add_sell("pf_t", "600519", sell)
    s = updated.holdings[0].sell_lots[0]
    assert s.avg_cost_at_sell == Decimal("1744.75")
    assert s.realized_pnl == Decimal("15505.00")
    assert updated.holdings[0].lots[0].quantity == 50
    assert updated.holdings[0].lots[1].quantity == 50


def test_add_sell_exceeds_position_raises():
    _seed_portfolio()
    _seed_holding("pf_t", "600519", [_lot("l1", 100, "1689.50")])
    sell = SellLot(
        sell_id="", sell_date=date(2026, 7, 19), quantity=150,
        sell_price=Decimal("1820.00"), fees=Decimal("0"),
        realized_pnl=Decimal("0"), avg_cost_at_sell=Decimal("0"),
    )
    with pytest.raises(ValueError, match="exceeds"):
        add_sell("pf_t", "600519", sell)


def test_add_sell_holding_not_found():
    _seed_portfolio()
    sell = SellLot(
        sell_id="", sell_date=date(2026, 7, 19), quantity=10,
        sell_price=Decimal("1820.00"), fees=Decimal("0"),
        realized_pnl=Decimal("0"), avg_cost_at_sell=Decimal("0"),
    )
    with pytest.raises(HoldingNotFound):
        add_sell("pf_t", "000001", sell)


def test_add_sell_full_position_empties_lots():
    _seed_portfolio()
    _seed_holding("pf_t", "600519", [_lot("l1", 100, "1689.50")])
    sell = SellLot(
        sell_id="", sell_date=date(2026, 7, 19), quantity=100,
        sell_price=Decimal("1820.00"), fees=Decimal("15.00"),
        realized_pnl=Decimal("0"), avg_cost_at_sell=Decimal("0"),
    )
    updated = add_sell("pf_t", "600519", sell)
    h = updated.holdings[0]
    assert len(h.sell_lots) == 1
    assert h.sell_lots[0].quantity == 100
