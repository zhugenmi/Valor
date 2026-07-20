"""Stub endpoints for valuecell-compatible API routes.

These return empty/default data to let the frontend load without 404s.
Replace with real implementations as each feature is developed.
"""

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/v1", tags=["Stubs"])

# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

AGENTS_LIST = {
    "agents": [
        {
            "agent_name": "ValorAgent",
            "display_name": "Valor Agent",
            "enabled": True,
            "description": "Valor Agent coordinates stock analysis agents for A-share investment research",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "agent_metadata": {"version": "1.0.0", "author": "Valor", "tags": ["valor", "super-agent"]},
        },
        {
            "agent_name": "sentiment_analysis",
            "display_name": "情绪分析",
            "enabled": True,
            "description": "分析市场情绪 (A股市场)",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "agent_metadata": {"version": "1.0.0", "author": "Valor", "tags": ["valor", "analysis"]},
        },
        {
            "agent_name": "technical_analyst",
            "display_name": "技术分析",
            "enabled": True,
            "description": "技术指标分析 (A股市场)",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "agent_metadata": {"version": "1.0.0", "author": "Valor", "tags": ["valor", "analysis"]},
        },
        {
            "agent_name": "fundamental_analysis",
            "display_name": "基本面分析",
            "enabled": True,
            "description": "基本面与财务分析 (A股市场)",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "agent_metadata": {"version": "1.0.0", "author": "Valor", "tags": ["valor", "analysis"]},
        },
    ]
}


@router.get("/agents/")
async def list_agents(enabled_only: str = "false", language: str = "en"):
    if enabled_only == "true":
        return {"code": 0, "data": {"agents": [a for a in AGENTS_LIST["agents"] if a["enabled"]]}, "msg": "ok"}
    return {"code": 0, "data": AGENTS_LIST, "msg": "ok"}


@router.get("/agents/by-name/{agent_name}")
async def agent_by_name(agent_name: str, language: str = "en"):
    for a in AGENTS_LIST["agents"]:
        if a["agent_name"] == agent_name:
            return {"code": 0, "data": a, "msg": "ok"}
    return {"code": 404, "data": None, "msg": "not found"}


@router.post("/agents/{agent_name}/enable")
async def enable_agent(agent_name: str, body: dict):
    return {"code": 0, "data": None, "msg": "ok"}


# ---------------------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------------------

WATCHLISTS = [
    {
        "name": "我的自选",
        "items": [
            {
                "ticker": "600519",
                "asset_type": "stock",
                "display_name": "贵州茅台",
                "symbol": "600519.SH",
                "exchange": "SSE",
            }
        ],
    }
]


@router.get("/watchlist/")
async def list_watchlist():
    return {"code": 0, "data": WATCHLISTS, "msg": "ok"}


@router.get("/watchlist/asset/search")
async def search_asset(q: str = "", language: str = "en"):
    return {"code": 0, "data": [], "msg": "ok"}


@router.post("/watchlist/asset")
async def add_watchlist_asset(body: dict):
    return {"code": 0, "data": None, "msg": "ok"}


@router.delete("/watchlist/asset/{ticker}")
async def delete_watchlist_asset(ticker: str):
    return {"code": 0, "data": None, "msg": "ok"}


@router.get("/watchlist/asset/{ticker}/price")
async def asset_price(ticker: str, request: Request):
    data_router = getattr(request.app.state, "data_router", None)
    price = 0.0
    change = 0.0
    timestamp = "2026-01-01T00:00:00Z"
    source = "stub"
    if data_router is not None:
        try:
            df = await data_router.get_realtime_quote(ticker)
            if df is not None and not df.empty:
                row = df.iloc[0]
                price = float(row.get("最新价", row.get("price", 0.0)) or 0.0)
                change = float(row.get("涨跌幅", row.get("change", 0.0)) or 0.0)
                source = "akshare"
                from datetime import UTC, datetime
                timestamp = datetime.now(UTC).isoformat()
        except Exception:
            pass  # fall back to stub defaults
    return {
        "code": 0,
        "data": {
            "ticker": ticker,
            "price": price,
            "price_formatted": f"{price:.2f}",
            "timestamp": timestamp,
            "change": change,
            "market_cap_formatted": "N/A",
            "source": source,
            "currency": "CNY",
        },
        "msg": "ok",
    }


@router.get("/watchlist/asset/{ticker}")
async def asset_detail(ticker: str, request: Request):
    data_router = getattr(request.app.state, "data_router", None)
    industry = ""
    pe_ratio = 0.0
    if data_router is not None:
        try:
            df = await data_router.get_financial_indicators(ticker)
            if df is not None and not df.empty:
                row = df.iloc[0]
                industry = str(row.get("行业", row.get("industry", "")) or "")
                pe_ratio = float(row.get("市盈率", row.get("pe", 0.0)) or 0.0)
        except Exception:
            pass
    return {
        "code": 0,
        "data": {
            "display_name": ticker,
            "properties": {
                "sector": "",
                "industry": industry,
                "market_cap": 0,
                "pe_ratio": pe_ratio,
                "dividend_yield": 0,
                "beta": 0,
                "website": "",
                "business_summary": "",
            },
        },
        "msg": "ok",
    }


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


@router.post("/analytics/event")
async def analytics_event(body: dict):
    """Stub: silently accept analytics events from the frontend."""
    return {"code": 0, "data": None, "msg": "ok"}
