"""Stock routes: historical price (real), price + detail (upgraded from stubs).

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from valor.server.envelope import fail, ok

router = APIRouter(prefix="/api/v1", tags=["Stock"])


def _row_to_history(df) -> list[dict]:
    """Convert daily history DataFrame to StockHistory[] items."""
    if df is None or df.empty:
        return []
    items: list[dict] = []
    for _, row in df.iterrows():
        time = str(row.get("date", row.get("时间", "")))
        price = float(row.get("close", row.get("收盘", 0.0)))
        items.append({"time": time, "price": price})
    return items


@router.get("/watchlist/asset/{ticker}/price/historical")
async def price_historical(ticker: str, request: Request, interval: str = "1d",
                           start_date: str = "", end_date: str = ""):
    """Historical daily prices. Only 1d supported for now."""
    if interval != "1d":
        return fail(1, "only 1d interval supported")
    data_router = getattr(request.app.state, "data_router", None)
    if data_router is None:
        return fail(1, "data source unavailable")
    try:
        df = await data_router.get_daily_history(ticker, start_date, end_date)
    except Exception as exc:
        return fail(1, f"data source unavailable: {exc}")
    return ok(_row_to_history(df))
