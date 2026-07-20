"""JSON file storage for portfolios. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations
import fcntl
import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from valor.portfolio.models import Holding, Lot, Portfolio, SellLot, Strategy

DATA_DIR: Path = Path(__file__).resolve().parents[2] / "data" / "portfolios"
_data_dir: Path = DATA_DIR


def set_data_dir(path: Path) -> None:
    global _data_dir
    _data_dir = Path(path)
    _data_dir.mkdir(parents=True, exist_ok=True)


def _get_data_dir() -> Path:
    d = Path(os.environ.get("VALOR_PORTFOLIO_DIR", "")) if os.environ.get("VALOR_PORTFOLIO_DIR") else _data_dir
    d.mkdir(parents=True, exist_ok=True)
    return d


def gen_portfolio_id() -> str:
    return f"pf_{uuid.uuid4().hex[:8]}"


def gen_strategy_id() -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"strat_{ts}_{uuid.uuid4().hex[:4]}"


def gen_lot_id() -> str:
    return f"lot_{uuid.uuid4().hex[:8]}"


def gen_sell_id() -> str:
    return f"sell_{uuid.uuid4().hex[:8]}"


class PortfolioNotFound(Exception):
    pass


def _path(portfolio_id: str) -> Path:
    return _get_data_dir() / f"{portfolio_id}.json"


@contextmanager
def _file_lock(portfolio_id: str):
    lock_path = _get_data_dir() / f"{portfolio_id}.lock"
    with open(lock_path, "w") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def _index_path() -> Path:
    return _get_data_dir() / "_index.json"


def load_index() -> list[dict]:
    p = _index_path()
    if not p.exists():
        return rebuild_index()
    return json.loads(p.read_text(encoding="utf-8"))


def rebuild_index() -> list[dict]:
    items = []
    for pf in list_portfolios():
        items.append({
            "portfolio_id": pf.portfolio_id,
            "name": pf.name,
            "updated_at": pf.updated_at.isoformat(),
        })
    _index_path().write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return items


def list_portfolios() -> list[Portfolio]:
    d = _get_data_dir()
    items = []
    for f in sorted(d.glob("pf_*.json")):
        items.append(Portfolio.model_validate_json(f.read_text(encoding="utf-8")))
    return items


def load_portfolio(portfolio_id: str) -> Portfolio:
    with _file_lock(portfolio_id):
        p = _path(portfolio_id)
        if not p.exists():
            raise PortfolioNotFound(portfolio_id)
        return Portfolio.model_validate_json(p.read_text(encoding="utf-8"))


def save_portfolio(portfolio: Portfolio) -> None:
    with _file_lock(portfolio.portfolio_id):
        portfolio.updated_at = datetime.now()
        p = _path(portfolio.portfolio_id)
        tmp = p.with_suffix(".json.tmp")
        bak = p.with_suffix(".json.bak")
        tmp.write_text(portfolio.model_dump_json(indent=2), encoding="utf-8")
        if p.exists():
            p.rename(bak)
        os.replace(tmp, p)
        if bak.exists():
            bak.unlink()


def delete_portfolio(portfolio_id: str) -> None:
    with _file_lock(portfolio_id):
        p = _path(portfolio_id)
        if not p.exists():
            raise PortfolioNotFound(portfolio_id)
        p.unlink()
        bak = p.with_suffix(".json.bak")
        if bak.exists():
            bak.unlink()


class HoldingNotFound(Exception):
    pass


class LotNotFound(Exception):
    pass


class StrategyNotFound(Exception):
    pass


def _find_holding_index(portfolio: Portfolio, ticker: str) -> int:
    for i, h in enumerate(portfolio.holdings):
        if h.ticker == ticker:
            return i
    return -1


def deduct_lots_weighted(
    lots: list[Lot], quantity_to_sell: int
) -> list[tuple[Lot, int]]:
    if quantity_to_sell <= 0:
        raise ValueError("sell quantity must be positive")
    total = sum(lot.quantity for lot in lots)
    if quantity_to_sell > total:
        raise ValueError(
            f"sell quantity exceeds position: requested={quantity_to_sell}, available={total}"
        )
    quotas = [
        (lot, quantity_to_sell * lot.quantity / total) for lot in lots
    ]
    int_alloc = [(lot, int(q)) for lot, q in quotas]
    allocated = sum(d for _, d in int_alloc)
    remainder = quantity_to_sell - allocated
    remainders = sorted(
        range(len(quotas)),
        key=lambda i: quotas[i][1] - int(quotas[i][1]),
        reverse=True,
    )
    for i in remainders[:remainder]:
        lot, d = int_alloc[i]
        int_alloc[i] = (lot, d + 1)
    result: list[tuple[Lot, int]] = []
    for lot, d in int_alloc:
        if d > 0:
            lot.quantity -= d
            result.append((lot, d))
    return result


def add_holding(portfolio_id: str, holding: Holding) -> Portfolio:
    with _file_lock(portfolio_id):
        p = _load_unlocked(portfolio_id)
        if _find_holding_index(p, holding.ticker) >= 0:
            idx = _find_holding_index(p, holding.ticker)
            p.holdings[idx].lots.extend(holding.lots)
        else:
            p.holdings.append(holding)
        _save_unlocked(p)
    return p


def _load_unlocked(portfolio_id: str) -> Portfolio:
    """Load portfolio WITHOUT acquiring the file lock — caller must hold the lock."""
    p = _path(portfolio_id)
    if not p.exists():
        raise PortfolioNotFound(portfolio_id)
    return Portfolio.model_validate_json(p.read_text(encoding="utf-8"))


def _save_unlocked(portfolio: Portfolio) -> None:
    """Save portfolio WITHOUT acquiring the file lock — caller must hold the lock."""
    portfolio.updated_at = datetime.now()
    p = _path(portfolio.portfolio_id)
    tmp = p.with_suffix(".json.tmp")
    bak = p.with_suffix(".json.bak")
    tmp.write_text(portfolio.model_dump_json(indent=2), encoding="utf-8")
    if p.exists():
        p.rename(bak)
    os.replace(tmp, p)
    if bak.exists():
        bak.unlink()


def _update_portfolio(portfolio_id: str, fn) -> Portfolio:
    """Load portfolio, apply fn(portfolio), save — all under one exclusive lock."""
    with _file_lock(portfolio_id):
        p = _load_unlocked(portfolio_id)
        fn(p)
        _save_unlocked(p)
    return p


def add_sell(portfolio_id: str, ticker: str, sell_lot: SellLot) -> Portfolio:
    def _do(p: Portfolio) -> None:
        idx = _find_holding_index(p, ticker)
        if idx < 0:
            raise HoldingNotFound(ticker)
        h = p.holdings[idx]
        total_qty = sum(lot.quantity for lot in h.lots)
        if sell_lot.quantity > total_qty:
            raise ValueError(
                f"sell quantity exceeds position: requested={sell_lot.quantity}, available={total_qty}"
            )
        total_cost = sum(lot.quantity * lot.cost_price for lot in h.lots)
        avg_cost = total_cost / Decimal(total_qty) if total_qty else Decimal("0")
        sell_lot.avg_cost_at_sell = avg_cost
        sell_lot.realized_pnl = (
            Decimal(sell_lot.quantity) * (sell_lot.sell_price - avg_cost)
            - sell_lot.fees
        )
        deduct_lots_weighted(h.lots, sell_lot.quantity)
        h.lots = [lot for lot in h.lots if lot.quantity > 0]
        if not sell_lot.sell_id:
            sell_lot.sell_id = gen_sell_id()
        h.sell_lots.append(sell_lot)

    return _update_portfolio(portfolio_id, _do)


def _cleanup_holding_if_empty(p: Portfolio, idx: int) -> None:
    h = p.holdings[idx]
    if not h.lots and not h.sell_lots:
        p.holdings.pop(idx)


def update_lot(
    portfolio_id: str, ticker: str, lot_id: str, patch: dict
) -> Portfolio:
    def _do(p: Portfolio) -> None:
        idx = _find_holding_index(p, ticker)
        if idx < 0:
            raise HoldingNotFound(ticker)
        h = p.holdings[idx]
        lot_index = next((i for i, lot in enumerate(h.lots) if lot.lot_id == lot_id), -1)
        if lot_index < 0:
            raise LotNotFound(lot_id)
        lot = h.lots[lot_index]
        for key, value in patch.items():
            if hasattr(lot, key) and value is not None:
                setattr(lot, key, value)
        if lot.quantity == 0:
            h.lots.pop(lot_index)
            _cleanup_holding_if_empty(p, idx)

    return _update_portfolio(portfolio_id, _do)


def remove_lot(portfolio_id: str, ticker: str, lot_id: str) -> Portfolio:
    def _do(p: Portfolio) -> None:
        idx = _find_holding_index(p, ticker)
        if idx < 0:
            raise HoldingNotFound(ticker)
        h = p.holdings[idx]
        lot_index = next((i for i, lot in enumerate(h.lots) if lot.lot_id == lot_id), -1)
        if lot_index < 0:
            raise LotNotFound(lot_id)
        h.lots.pop(lot_index)
        _cleanup_holding_if_empty(p, idx)

    return _update_portfolio(portfolio_id, _do)


def update_holding(portfolio_id: str, ticker: str, holding: Holding) -> Portfolio:
    def _do(p: Portfolio) -> None:
        idx = _find_holding_index(p, ticker)
        if idx < 0:
            raise HoldingNotFound(ticker)
        p.holdings[idx] = holding

    return _update_portfolio(portfolio_id, _do)


def remove_holding(portfolio_id: str, ticker: str) -> Portfolio:
    def _do(p: Portfolio) -> None:
        idx = _find_holding_index(p, ticker)
        if idx < 0:
            raise HoldingNotFound(ticker)
        p.holdings.pop(idx)

    return _update_portfolio(portfolio_id, _do)


def add_lot_to_holding(portfolio_id: str, ticker: str, lot: Lot) -> Portfolio:
    """Add a single lot to an existing holding, under one exclusive lock."""
    def _do(p: Portfolio) -> None:
        idx = _find_holding_index(p, ticker)
        if idx < 0:
            raise HoldingNotFound(ticker)
        if not lot.lot_id:
            lot.lot_id = gen_lot_id()
        p.holdings[idx].lots.append(lot)

    return _update_portfolio(portfolio_id, _do)


def add_strategy(portfolio_id: str, strategy: Strategy) -> Portfolio:
    def _do(p: Portfolio) -> None:
        p.strategies.append(strategy)

    return _update_portfolio(portfolio_id, _do)


def remove_strategy(portfolio_id: str, strategy_id: str) -> Portfolio:
    def _do(p: Portfolio) -> None:
        for i, s in enumerate(p.strategies):
            if s.strategy_id == strategy_id:
                p.strategies.pop(i)
                return
        raise StrategyNotFound(strategy_id)

    return _update_portfolio(portfolio_id, _do)
