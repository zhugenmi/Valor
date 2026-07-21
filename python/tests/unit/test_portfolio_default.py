"""Unit tests for default portfolio lookup in stream.py.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from valor.portfolio.models import Holding, Lot, Portfolio
from valor.server.routes.stream import _load_default_portfolio


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
