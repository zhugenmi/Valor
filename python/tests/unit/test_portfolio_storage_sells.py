"""Tests for sell-lot storage operations. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from datetime import date
from decimal import Decimal
import pytest
from valor.portfolio.models import Lot
from valor.portfolio.storage import (
    DATA_DIR, deduct_lots_weighted, gen_sell_id, set_data_dir,
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
