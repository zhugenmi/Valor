"""Tool registry + handlers for Agent Runtime.

Each tool wraps an existing capability (KB search, data adapter, LangGraph
workflow) without modifying it. Handlers validate inputs, call the underlying
function, and return a dict result (or {"error": ...} on failure).

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from loguru import logger

from valor.adapters.llm.protocol import ToolSchema

# Imports of existing capabilities (do NOT modify these modules)
# - kb_search_search: sync function returning list[dict]
# - get_market_data / get_financial_metrics: sync functions in valor.tools.api
#   returning dict / list[dict] respectively (wrappers around akshare_cache).
#   We use these instead of DataRouter (async, returns DataFrame) for simplicity;
#   they're the same wrappers the existing agents use.
from valor.tools.kb_search import search as kb_search_search  # noqa: E402
from valor.tools.api import (  # noqa: E402
    get_financial_metrics,
    get_market_data,
)
from valor.agents.workflow import run_analysis, run_agents  # noqa: E402

# A-share ticker: 6 digits, first digit 0/3/6 (SZ main/SZ growth/SH main)
_TICKER_RE = re.compile(r"^[036]\d{5}$")

_VALID_SINGLE_AGENTS = frozenset({
    "technicals", "fundamentals", "valuation", "capital_sentiment", "macro_industry",
})


@dataclass
class Tool:
    """A registered tool: schema + async handler."""
    schema: ToolSchema
    handler: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def _validate_ticker(ticker: str | None) -> str | None:
    """Return error message if ticker is invalid; None if valid."""
    if not ticker or not isinstance(ticker, str):
        return "ticker is required (6-digit A-share code, e.g. 600519)"
    if not _TICKER_RE.fullmatch(ticker.strip()):
        return f"invalid ticker '{ticker}': must be 6-digit A-share code (e.g. 600519)"
    return None


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

async def handle_kb_search(arguments: dict[str, Any]) -> dict[str, Any]:
    """Search the knowledge base. Returns {"chunks": [...]} or {"error": ...}."""
    query = arguments.get("query")
    if not query or not isinstance(query, str) or not query.strip():
        return {"error": "kb_search requires 'query' (non-empty string)"}
    top_k = arguments.get("top_k", 5)
    if not isinstance(top_k, int) or top_k < 1:
        top_k = 5
    try:
        chunks = await asyncio.to_thread(kb_search_search, query, top_k)
    except Exception as exc:
        logger.exception("kb_search handler failed")
        return {"error": f"kb_search failed: {exc}"}
    return {"chunks": chunks, "query": query}


async def handle_get_stock_data(arguments: dict[str, Any]) -> dict[str, Any]:
    """Fetch market data (price, market_cap, volume) + financial indicators for a ticker.

    Uses valor.tools.api sync wrappers (same as existing agents); runs in
    thread to avoid blocking the event loop. Returns dict with quote/financials.
    """
    ticker = arguments.get("ticker")
    if err := _validate_ticker(ticker):
        return {"error": err}
    ticker = ticker.strip()  # type: ignore[union-attr]
    try:
        quote = await asyncio.to_thread(get_market_data, ticker)
        financials = await asyncio.to_thread(get_financial_metrics, ticker)
    except Exception as exc:
        logger.exception("get_stock_data handler failed")
        return {"error": f"get_stock_data failed: {exc}"}
    # Note: get_market_data may return dict; get_financial_metrics returns list[dict].
    # Both are JSON-serializable.
    return {"ticker": ticker, "quote": quote, "financials": financials}


async def handle_run_single_agent(arguments: dict[str, Any]) -> dict[str, Any]:
    """Run market_data + one analysis agent. Returns the agent's output."""
    ticker = arguments.get("ticker")
    if err := _validate_ticker(ticker):
        return {"error": err}
    ticker = ticker.strip()  # type: ignore[union-attr]
    agent_name = arguments.get("agent_name")
    if not agent_name or agent_name not in _VALID_SINGLE_AGENTS:
        return {
            "error": f"invalid agent_name '{agent_name}'; valid: {sorted(_VALID_SINGLE_AGENTS)}",
        }
    try:
        # run_agents is sync (LangGraph compiled.invoke); run in thread
        state = await asyncio.to_thread(
            run_agents, ticker=ticker, agent_names=[agent_name],
        )
    except Exception as exc:
        logger.exception("run_single_agent handler failed")
        return {"error": f"run_single_agent failed: {exc}"}

    # Extract the agent's HumanMessage by name
    target_name_map = {
        "technicals": "technical_analyst_agent",
        "fundamentals": "fundamentals_agent",
        "valuation": "valuation_agent",
        "capital_sentiment": "capital_sentiment_agent",
        "macro_industry": "macro_industry_agent",
    }
    target = target_name_map[agent_name]
    output: dict[str, Any] = {}
    for msg in reversed(state.get("messages", [])):
        if getattr(msg, "name", None) == target:
            try:
                output = json.loads(msg.content)
            except (json.JSONDecodeError, TypeError, AttributeError):
                output = {"raw": str(getattr(msg, "content", ""))}
            break
    return {"agent": agent_name, "ticker": ticker, "output": output}


async def handle_run_full_analysis(arguments: dict[str, Any]) -> dict[str, Any]:
    """Run the complete 9-node LangGraph workflow. Returns final decision."""
    ticker = arguments.get("ticker")
    if err := _validate_ticker(ticker):
        return {"error": err}
    ticker = ticker.strip()  # type: ignore[union-attr]
    try:
        state = await asyncio.to_thread(run_analysis, ticker=ticker)
    except Exception as exc:
        logger.exception("run_full_analysis handler failed")
        return {"error": f"run_full_analysis failed: {exc}"}

    # Extract portfolio_management_agent's final message as final_decision
    final_decision: dict[str, Any] | None = None
    for msg in reversed(state.get("messages", [])):
        if getattr(msg, "name", None) == "portfolio_management_agent":
            try:
                final_decision = json.loads(msg.content)
            except (json.JSONDecodeError, TypeError, AttributeError):
                final_decision = {"raw": str(getattr(msg, "content", ""))}
            break
    return {"ticker": ticker, "final_decision": final_decision or {}}


# ---------------------------------------------------------------------------
# Tool schemas (OpenAI function-calling format)
# ---------------------------------------------------------------------------

_KB_SEARCH_SCHEMA = ToolSchema(
    name="kb_search",
    description=(
        "Search the Valor knowledge base (RAG) for research reports, "
        "disclosure documents, and regulatory filings. Use when the user "
        "asks about specific companies, industries, or financial concepts "
        "that may be covered by uploaded documents. Returns chunks with "
        "doc_title, publish_date, and text."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query in natural language (Chinese or English).",
            },
            "top_k": {
                "type": "integer",
                "description": "Number of chunks to return (default 5, max 10).",
                "default": 5,
            },
        },
        "required": ["query"],
    },
)

_GET_STOCK_DATA_SCHEMA = ToolSchema(
    name="get_stock_data",
    description=(
        "Fetch realtime quote (price, volume, market_cap) and financial "
        "indicators (ROE, net margin, PE, PB, etc.) for an A-share ticker. "
        "Use before running analysis agents, or when the user asks about "
        "current price, valuation ratios, or financial metrics."
    ),
    parameters={
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "6-digit A-share ticker code, e.g. '600519' (贵州茅台).",
            },
        },
        "required": ["ticker"],
    },
)

_RUN_SINGLE_AGENT_SCHEMA = ToolSchema(
    name="run_single_agent",
    description=(
        "Run one specialist analysis agent (technical / fundamental / "
        "valuation / capital_sentiment / macro_industry) for a ticker. "
        "Use when the user asks about a specific dimension only (e.g. "
        "'600519 technical analysis'). Returns the agent's signal and reasoning."
    ),
    parameters={
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "6-digit A-share ticker code. Required except for macro_industry.",
            },
            "agent_name": {
                "type": "string",
                "enum": ["technicals", "fundamentals", "valuation", "capital_sentiment", "macro_industry"],
                "description": "Which specialist agent to run.",
            },
        },
        "required": ["ticker", "agent_name"],
    },
)

_RUN_FULL_ANALYSIS_SCHEMA = ToolSchema(
    name="run_full_analysis",
    description=(
        "Run the complete 9-node Valor analysis workflow for a ticker: "
        "market_data -> [technicals, fundamentals, valuation, capital_sentiment, "
        "macro_industry] -> bull_bear_debate -> risk_manager -> portfolio_manager. "
        "Use when the user asks for a full diagnosis or buy/sell decision "
        "(e.g. '分析600519', '诊断贵州茅台'). Returns final_decision with "
        "action (buy/sell/hold), quantity, and confidence."
    ),
    parameters={
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "6-digit A-share ticker code, e.g. '600519'.",
            },
        },
        "required": ["ticker"],
    },
)


def get_default_tools() -> list[Tool]:
    """Return the 4 registered tools."""
    return [
        Tool(schema=_KB_SEARCH_SCHEMA, handler=handle_kb_search),
        Tool(schema=_GET_STOCK_DATA_SCHEMA, handler=handle_get_stock_data),
        Tool(schema=_RUN_SINGLE_AGENT_SCHEMA, handler=handle_run_single_agent),
        Tool(schema=_RUN_FULL_ANALYSIS_SCHEMA, handler=handle_run_full_analysis),
    ]


async def execute_tool(tool: Tool, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute a tool's handler with error isolation."""
    try:
        return await tool.handler(arguments)
    except Exception as exc:
        logger.exception(f"Tool '{tool.schema.name}' raised unexpectedly")
        return {"error": f"tool '{tool.schema.name}' crashed: {exc}"}


__all__ = [
    "Tool",
    "execute_tool",
    "get_default_tools",
    "handle_kb_search",
    "handle_get_stock_data",
    "handle_run_single_agent",
    "handle_run_full_analysis",
]