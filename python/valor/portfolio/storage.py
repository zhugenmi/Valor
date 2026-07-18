"""JSON file storage for portfolios. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations
import fcntl
import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from valor.portfolio.models import Holding, Portfolio, Strategy

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


class StrategyNotFound(Exception):
    pass


def _find_holding_index(portfolio: Portfolio, ticker: str) -> int:
    for i, h in enumerate(portfolio.holdings):
        if h.ticker == ticker:
            return i
    return -1


def add_holding(portfolio_id: str, holding: Holding) -> Portfolio:
    p = load_portfolio(portfolio_id)
    if _find_holding_index(p, holding.ticker) >= 0:
        idx = _find_holding_index(p, holding.ticker)
        p.holdings[idx].lots.extend(holding.lots)
    else:
        p.holdings.append(holding)
    save_portfolio(p)
    return p


def update_holding(portfolio_id: str, ticker: str, holding: Holding) -> Portfolio:
    p = load_portfolio(portfolio_id)
    idx = _find_holding_index(p, ticker)
    if idx < 0:
        raise HoldingNotFound(ticker)
    p.holdings[idx] = holding
    save_portfolio(p)
    return p


def remove_holding(portfolio_id: str, ticker: str) -> Portfolio:
    p = load_portfolio(portfolio_id)
    idx = _find_holding_index(p, ticker)
    if idx < 0:
        raise HoldingNotFound(ticker)
    p.holdings.pop(idx)
    save_portfolio(p)
    return p


def add_strategy(portfolio_id: str, strategy: Strategy) -> Portfolio:
    p = load_portfolio(portfolio_id)
    p.strategies.append(strategy)
    save_portfolio(p)
    return p


def remove_strategy(portfolio_id: str, strategy_id: str) -> Portfolio:
    p = load_portfolio(portfolio_id)
    for i, s in enumerate(p.strategies):
        if s.strategy_id == strategy_id:
            p.strategies.pop(i)
            save_portfolio(p)
            return p
    raise StrategyNotFound(strategy_id)
