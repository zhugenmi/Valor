"""System routes: default tickers for homepage display.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from fastapi import APIRouter

from valor.server.envelope import ok

router = APIRouter(prefix="/api/v1", tags=["System"])

_REGION_TICKERS: dict[str, list[dict]] = {
    "cn": [
        {"ticker": "000001", "symbol": "000001.SH", "name": "上证指数"},
        {"ticker": "399001", "symbol": "399001.SZ", "name": "深证成指"},
        {"ticker": "399006", "symbol": "399006.SZ", "name": "创业板指"},
    ],
    "default": [
        {"ticker": "000001", "symbol": "000001.SH", "name": "上证指数"},
        {"ticker": "^DJI", "symbol": "^DJI", "name": "道琼斯"},
        {"ticker": "^GSPC", "symbol": "^GSPC", "name": "标普500"},
        {"ticker": "^IXIC", "symbol": "^IXIC", "name": "纳斯达克"},
    ],
}


@router.get("/system/default-tickers")
async def default_tickers(region: str | None = None, language: str = "en"):
    """Return region-aware default tickers for homepage."""
    if region is None:
        region = "cn" if language == "zh" else "default"
    if region not in _REGION_TICKERS:
        region = "default"
    return ok({"region": region, "tickers": _REGION_TICKERS[region]})
