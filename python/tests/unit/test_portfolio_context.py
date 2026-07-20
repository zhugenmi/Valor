"""Tests for portfolio_context loader. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

from valor.portfolio.models import Holding, Lot, Portfolio
from valor.portfolio.storage import PortfolioNotFound
from valor.server.portfolio_context import load_portfolio_context


def _build_portfolio(cash: float, holdings: list[Holding]) -> Portfolio:
    return Portfolio(
        portfolio_id="pf_test1",
        name="test",
        cash=Decimal(str(cash)),
        holdings=holdings,
        strategies=[],
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


def _build_holding(ticker: str, qty: int) -> Holding:
    return Holding(
        ticker=ticker,
        name=ticker,
        lots=[Lot(lot_id="lot_test", open_date=date.today(), quantity=qty, cost_price=Decimal("0"))],
        sell_lots=[],
    )


def test_returns_cash_and_stock_quantity():
    pf = _build_portfolio(50000.0, [_build_holding("600519", 100), _build_holding("000001", 200)])
    with patch("valor.server.portfolio_context.load_portfolio", return_value=pf):
        result = load_portfolio_context("pf_test1", "600519")
    assert result == {"cash": 50000.0, "stock": 100}


def test_ticker_not_in_holdings_returns_zero_stock():
    pf = _build_portfolio(50000.0, [_build_holding("000001", 200)])
    with patch("valor.server.portfolio_context.load_portfolio", return_value=pf):
        result = load_portfolio_context("pf_test1", "600519")
    assert result == {"cash": 50000.0, "stock": 0}


def test_portfolio_not_found_propagates():
    with patch(
        "valor.server.portfolio_context.load_portfolio",
        side_effect=PortfolioNotFound("pf_missing"),
    ):
        with pytest.raises(PortfolioNotFound):
            load_portfolio_context("pf_missing", "600519")


def test_aggregates_quantity_across_lots():
    """quantity is computed from the holding's lots array; verify aggregation
    across multiple lots works correctly."""
    h = Holding(
        ticker="600519",
        name="600519",
        lots=[
            Lot(lot_id="lot_a", open_date=date.today(), quantity=200, cost_price=Decimal("100")),
            Lot(lot_id="lot_b", open_date=date.today(), quantity=150, cost_price=Decimal("110")),
        ],
        sell_lots=[],
    )
    pf = _build_portfolio(0.0, [h])
    with patch("valor.server.portfolio_context.load_portfolio", return_value=pf):
        result = load_portfolio_context("pf_test1", "600519")
    assert result["stock"] == 350