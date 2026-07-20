"""Load portfolio context for the workflow's portfolio_manager node.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial.
"""
from __future__ import annotations

from decimal import Decimal

from valor.portfolio.storage import PortfolioNotFound, load_portfolio


def load_portfolio_context(portfolio_id: str, ticker: str) -> dict:
    """Return {'cash': float, 'stock': int} for the given portfolio + ticker.

    Raises PortfolioNotFound if portfolio_id doesn't exist.
    stock is the holding's quantity for ticker (0 if not held).
    Quantity is computed from the holding's lots array.
    """
    pf = load_portfolio(portfolio_id)
    cash = float(pf.cash) if isinstance(pf.cash, Decimal) else float(pf.cash or 0.0)
    stock = 0
    for h in pf.holdings:
        if h.ticker == ticker:
            stock = sum(lot.quantity for lot in h.lots)
            break
    return {"cash": cash, "stock": stock}


__all__ = ["load_portfolio_context", "PortfolioNotFound"]