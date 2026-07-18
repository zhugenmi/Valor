from datetime import date, datetime
from decimal import Decimal
import pytest
from valor.portfolio.models import Holding, Lot, Portfolio, Strategy
import threading
from valor.portfolio.storage import (
    add_holding, add_strategy, list_portfolios, load_portfolio, load_index,
    rebuild_index, remove_holding, remove_strategy, save_portfolio,
    delete_portfolio, PortfolioNotFound, HoldingNotFound, StrategyNotFound,
    gen_portfolio_id, DATA_DIR, set_data_dir, update_holding,
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
