"""Portfolio storage operations, including sell-lot storage.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from datetime import date, datetime
from decimal import Decimal
import threading

import pytest

from valor.portfolio.models import Holding, Lot, Portfolio, SellLot, Strategy
from valor.portfolio.storage import (
    DATA_DIR, add_holding, add_sell, add_strategy, deduct_lots_weighted,
    delete_portfolio, gen_portfolio_id, gen_sell_id, list_portfolios,
    load_index, load_portfolio, rebuild_index, remove_holding, remove_lot,
    remove_strategy, save_portfolio, set_data_dir, update_holding, update_lot,
    HoldingNotFound, LotNotFound, PortfolioNotFound, StrategyNotFound,
)


@pytest.fixture
def tmp_dir(tmp_path, monkeypatch):
    set_data_dir(tmp_path)
    yield tmp_path
    set_data_dir(DATA_DIR)


def test_gen_portfolio_id_prefix():
    pid = gen_portfolio_id()
    assert pid.startswith("pf_")


def test_save_and_load_roundtrip(tmp_dir):
    p = Portfolio(portfolio_id="pf_x", name="main", cash=Decimal("1000"),
                  created_at=datetime(2026, 7, 17, 10, 0), updated_at=datetime(2026, 7, 17, 10, 0))
    save_portfolio(p)
    loaded = load_portfolio("pf_x")
    assert loaded.name == "main"
    assert loaded.cash == Decimal("1000")


def test_load_not_found(tmp_dir):
    with pytest.raises(PortfolioNotFound):
        load_portfolio("pf_missing")


def test_list_portfolios(tmp_dir):
    for i in range(3):
        p = Portfolio(portfolio_id=f"pf_{i}", name=f"p{i}",
                      created_at=datetime(2026, 7, 17), updated_at=datetime(2026, 7, 17))
        save_portfolio(p)
    items = list_portfolios()
    assert len(items) == 3
    assert all(item.portfolio_id.startswith("pf_") for item in items)


def test_delete_portfolio(tmp_dir):
    p = Portfolio(portfolio_id="pf_del", name="x",
                  created_at=datetime(2026, 7, 17), updated_at=datetime(2026, 7, 17))
    save_portfolio(p)
    delete_portfolio("pf_del")
    with pytest.raises(PortfolioNotFound):
        load_portfolio("pf_del")


def _seed(tmp_dir):
    p = Portfolio(portfolio_id="pf_t", name="t", created_at=datetime(2026, 7, 17), updated_at=datetime(2026, 7, 17))
    save_portfolio(p)
    return p


def test_add_holding(tmp_dir):
    _seed(tmp_dir)
    h = Holding(ticker="600519", name="贵州茅台", lots=[Lot(lot_id="l1", open_date=date(2024, 1, 1), quantity=100, cost_price=Decimal("1689.50"))])
    updated = add_holding("pf_t", h)
    assert len(updated.holdings) == 1
    loaded = load_portfolio("pf_t")
    assert loaded.holdings[0].ticker == "600519"


def test_update_holding(tmp_dir):
    _seed(tmp_dir)
    h = Holding(ticker="600519", lots=[])
    add_holding("pf_t", h)
    h2 = Holding(ticker="600519", name="新名字", lots=[])
    update_holding("pf_t", "600519", h2)
    assert load_portfolio("pf_t").holdings[0].name == "新名字"


def test_update_holding_not_found(tmp_dir):
    _seed(tmp_dir)
    with pytest.raises(HoldingNotFound):
        update_holding("pf_t", "000001", Holding(ticker="000001", lots=[]))


def test_remove_holding(tmp_dir):
    _seed(tmp_dir)
    add_holding("pf_t", Holding(ticker="600519", lots=[]))
    remove_holding("pf_t", "600519")
    assert len(load_portfolio("pf_t").holdings) == 0


def test_add_strategy(tmp_dir):
    _seed(tmp_dir)
    s = Strategy(strategy_id="strat_1", name="均衡", method="equal_weight",
                 target_weights={"600519": 1.0}, rationale="测试",
                 created_at=datetime(2026, 7, 17))
    add_strategy("pf_t", s)
    assert len(load_portfolio("pf_t").strategies) == 1


def test_remove_strategy(tmp_dir):
    _seed(tmp_dir)
    s = Strategy(strategy_id="strat_1", name="均衡", method="equal_weight",
                 target_weights={}, rationale="", created_at=datetime(2026, 7, 17))
    add_strategy("pf_t", s)
    remove_strategy("pf_t", "strat_1")
    assert len(load_portfolio("pf_t").strategies) == 0


def test_remove_strategy_not_found(tmp_dir):
    _seed(tmp_dir)
    with pytest.raises(StrategyNotFound):
        remove_strategy("pf_t", "strat_missing")


def test_add_holding_existing_ticker_merges_lots(tmp_dir):
    """Adding a holding with an existing ticker merges lots instead of duplicating."""
    _seed(tmp_dir)
    h1 = Holding(ticker="600519", lots=[Lot(lot_id="l1", open_date=date(2024, 1, 1), quantity=100, cost_price=Decimal("10"))])
    add_holding("pf_t", h1)
    h2 = Holding(ticker="600519", lots=[Lot(lot_id="l2", open_date=date(2024, 6, 1), quantity=50, cost_price=Decimal("12"))])
    add_holding("pf_t", h2)
    loaded = load_portfolio("pf_t")
    assert len(loaded.holdings) == 1
    assert len(loaded.holdings[0].lots) == 2


def test_concurrent_writes_serialized(tmp_dir):
    p = Portfolio(portfolio_id="pf_concurrent", name="c",
                  created_at=datetime(2026, 7, 17), updated_at=datetime(2026, 7, 17))
    save_portfolio(p)
    errors = []
    def write_loop():
        try:
            for _ in range(5):
                loaded = load_portfolio("pf_concurrent")
                loaded.name = f"updated_by_{threading.get_ident()}"
                save_portfolio(loaded)
        except Exception as e:
            errors.append(e)
    threads = [threading.Thread(target=write_loop) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    final = load_portfolio("pf_concurrent")
    assert final.name.startswith("updated_by_")


def test_index_rebuild(tmp_dir):
    for i in range(2):
        p = Portfolio(portfolio_id=f"pf_idx_{i}", name=f"p{i}",
                      created_at=datetime(2026, 7, 17), updated_at=datetime(2026, 7, 17))
        save_portfolio(p)
    rebuild_index()
    idx = load_index()
    assert len(idx) == 2
    assert "pf_idx_0" in [item["portfolio_id"] for item in idx]


def test_index_rebuild_empty(tmp_dir):
    """Rebuilding index on an empty dir returns empty list."""
    idx = rebuild_index()
    assert idx == []


# --- sell-lot storage ---


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


def test_update_lot_partial_fields():
    _seed_portfolio()
    _seed_holding("pf_t", "600519", [_lot("l1", 100, "1689.50")])
    updated = update_lot("pf_t", "600519", "l1", {"cost_price": Decimal("1700.00"), "fees": Decimal("12.50")})
    lot = updated.holdings[0].lots[0]
    assert lot.cost_price == Decimal("1700.00")
    assert lot.fees == Decimal("12.50")
    assert lot.quantity == 100
    assert lot.open_date == date(2024, 1, 1)


def test_update_lot_quantity_to_zero_removes_lot():
    _seed_portfolio()
    _seed_holding("pf_t", "600519", [
        _lot("l1", 100, "1689.50"),
        _lot("l2", 50, "1700.00"),
    ])
    updated = update_lot("pf_t", "600519", "l1", {"quantity": 0})
    assert len(updated.holdings[0].lots) == 1
    assert updated.holdings[0].lots[0].lot_id == "l2"


def test_update_lot_quantity_to_zero_deletes_holding_when_no_sell_lots():
    _seed_portfolio()
    _seed_holding("pf_t", "600519", [_lot("l1", 100, "1689.50")])
    updated = update_lot("pf_t", "600519", "l1", {"quantity": 0})
    assert len(updated.holdings) == 0


def test_update_lot_quantity_to_zero_keeps_holding_when_has_sell_lots():
    _seed_portfolio()
    _seed_holding("pf_t", "600519", [_lot("l1", 100, "1689.50")])
    add_sell("pf_t", "600519", SellLot(
        sell_id="", sell_date=date(2026, 7, 19), quantity=50,
        sell_price=Decimal("1820.00"), fees=Decimal("5.00"),
        realized_pnl=Decimal("0"), avg_cost_at_sell=Decimal("0"),
    ))
    updated = update_lot("pf_t", "600519", "l1", {"quantity": 0})
    assert len(updated.holdings) == 1
    assert len(updated.holdings[0].sell_lots) == 1
    assert len(updated.holdings[0].lots) == 0


def test_update_lot_not_found():
    _seed_portfolio()
    _seed_holding("pf_t", "600519", [_lot("l1", 100, "1689.50")])
    with pytest.raises(LotNotFound):
        update_lot("pf_t", "600519", "l_missing", {"quantity": 50})


def test_update_lot_holding_not_found():
    _seed_portfolio()
    with pytest.raises(HoldingNotFound):
        update_lot("pf_t", "000001", "l1", {"quantity": 50})


def test_remove_lot_basic():
    _seed_portfolio()
    _seed_holding("pf_t", "600519", [
        _lot("l1", 100, "1689.50"),
        _lot("l2", 50, "1700.00"),
    ])
    updated = remove_lot("pf_t", "600519", "l1")
    assert len(updated.holdings[0].lots) == 1
    assert updated.holdings[0].lots[0].lot_id == "l2"


def test_remove_last_lot_no_sell_lots_deletes_holding():
    _seed_portfolio()
    _seed_holding("pf_t", "600519", [_lot("l1", 100, "1689.50")])
    updated = remove_lot("pf_t", "600519", "l1")
    assert len(updated.holdings) == 0


def test_remove_last_lot_with_sell_lots_keeps_holding():
    _seed_portfolio()
    _seed_holding("pf_t", "600519", [_lot("l1", 100, "1689.50")])
    add_sell("pf_t", "600519", SellLot(
        sell_id="", sell_date=date(2026, 7, 19), quantity=50,
        sell_price=Decimal("1820.00"), fees=Decimal("5.00"),
        realized_pnl=Decimal("0"), avg_cost_at_sell=Decimal("0"),
    ))
    updated = remove_lot("pf_t", "600519", "l1")
    assert len(updated.holdings) == 1
    assert len(updated.holdings[0].sell_lots) == 1
    assert len(updated.holdings[0].lots) == 0


def test_remove_lot_not_found():
    _seed_portfolio()
    _seed_holding("pf_t", "600519", [_lot("l1", 100, "1689.50")])
    with pytest.raises(LotNotFound):
        remove_lot("pf_t", "600519", "l_missing")


def test_remove_lot_holding_not_found():
    _seed_portfolio()
    with pytest.raises(HoldingNotFound):
        remove_lot("pf_t", "000001", "l1")