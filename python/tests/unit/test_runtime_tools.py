"""Test runtime tool registry + handlers.
License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial"""
from __future__ import annotations

from unittest.mock import patch

from valor.runtime.tools import (
    Tool,
    execute_tool,
    get_default_tools,
    handle_get_stock_data,
    handle_kb_search,
    handle_run_full_analysis,
    handle_run_single_agent,
)


def test_get_default_tools_returns_four_tools():
    tools = get_default_tools()
    assert len(tools) == 4
    names = {t.schema.name for t in tools}
    assert names == {"kb_search", "get_stock_data", "run_full_analysis", "run_single_agent"}


def test_tool_schemas_have_required_fields():
    tools = get_default_tools()
    for t in tools:
        assert t.schema.name
        assert t.schema.description
        assert t.schema.parameters["type"] == "object"
        assert "properties" in t.schema.parameters


def test_kb_search_schema_has_query_param():
    tools = get_default_tools()
    kb = next(t for t in tools if t.schema.name == "kb_search")
    assert "query" in kb.schema.parameters["properties"]
    assert "query" in kb.schema.parameters["required"]


def test_get_stock_data_schema_requires_ticker():
    tools = get_default_tools()
    sd = next(t for t in tools if t.schema.name == "get_stock_data")
    assert "ticker" in sd.schema.parameters["required"]


async def test_handle_kb_search_returns_chunks(monkeypatch):
    """kb_search handler 调用 valor.tools.kb_search.search 并返回 list。"""
    fake_chunks = [{"chunk_id": "c1", "doc_title": "茅台研究", "text": "..."}]
    with patch("valor.runtime.tools.kb_search_search", return_value=fake_chunks):
        result = await handle_kb_search({"query": "茅台", "top_k": 5})
    assert isinstance(result, dict)
    assert "chunks" in result
    assert result["chunks"] == fake_chunks


async def test_handle_kb_search_invalid_args_returns_error():
    result = await handle_kb_search({})
    assert "error" in result
    assert "query" in result["error"]


async def test_handle_get_stock_data_valid_ticker(monkeypatch):
    fake_quote = {"market_cap": 100e8, "volume": 1000000, "price": 1685.0}
    fake_fin = [{"return_on_equity": 0.25, "pe_ratio": 30.0}]
    with (
        patch("valor.runtime.tools.get_market_data", return_value=fake_quote),
        patch("valor.runtime.tools.get_financial_metrics", return_value=fake_fin),
    ):
        result = await handle_get_stock_data({"ticker": "600519"})
    assert result["ticker"] == "600519"
    assert result["quote"]["price"] == 1685.0
    assert result["financials"] == fake_fin


async def test_handle_get_stock_data_invalid_ticker_returns_error():
    result = await handle_get_stock_data({"ticker": "123"})
    assert "error" in result
    assert "6位" in result["error"] or "invalid" in result["error"].lower()


async def test_handle_run_single_agent_valid(monkeypatch):
    """run_single_agent handler 调用 workflow.run_agents 并提取该 agent 的 message。"""
    from langchain_core.messages import HumanMessage

    fake_state = {
        "messages": [
            HumanMessage(
                content='{"signal":"bullish","confidence":0.7}',
                name="technical_analyst_agent",
            ),
        ],
        "data": {},
        "metadata": {},
    }
    with patch("valor.runtime.tools.run_agents", return_value=fake_state):
        result = await handle_run_single_agent({"ticker": "600519", "agent_name": "technicals"})
    assert result["agent"] == "technicals"
    assert result["ticker"] == "600519"
    assert result["output"]["signal"] == "bullish"


async def test_handle_run_single_agent_invalid_name_returns_error():
    result = await handle_run_single_agent({"ticker": "600519", "agent_name": "invalid_agent"})
    assert "error" in result


async def test_handle_run_full_analysis_returns_final_decision(monkeypatch):
    """run_full_analysis handler 调用 workflow.run_analysis 并提取 portfolio_manager message。"""
    from langchain_core.messages import HumanMessage

    fake_state = {
        "messages": [
            HumanMessage(
                content='{"action":"buy","quantity":100,"confidence":0.72}',
                name="portfolio_management_agent",
            ),
        ],
        "data": {"ticker": "600519"},
        "metadata": {},
    }
    with patch("valor.runtime.tools.run_analysis", return_value=fake_state):
        result = await handle_run_full_analysis({"ticker": "600519"})
    assert result["ticker"] == "600519"
    assert result["final_decision"]["action"] == "buy"
    assert result["final_decision"]["quantity"] == 100


async def test_execute_tool_dispatches_to_handler():
    """execute_tool 根据 tool name 找到 handler 并执行。"""
    tool = next(t for t in get_default_tools() if t.schema.name == "kb_search")
    fake_chunks = [{"chunk_id": "c1"}]
    with patch("valor.runtime.tools.kb_search_search", return_value=fake_chunks):
        result = await execute_tool(tool, {"query": "茅台"})
    assert result["chunks"] == fake_chunks


async def test_execute_tool_unknown_tool_returns_error():
    """execute_tool 找不到 tool 时返回 error。"""
    fake_tool = Tool.__new__(Tool)
    fake_tool.schema = type("S", (), {"name": "nonexistent"})()
    result = await execute_tool(fake_tool, {})
    assert "error" in result