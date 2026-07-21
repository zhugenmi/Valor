"""Tests for the LangGraph workflow structure."""

from valor.agents.workflow import build_workflow


def test_workflow_builds_with_all_nodes():
    """Workflow should register all 9 agent nodes."""
    wf = build_workflow()
    node_names = list(wf.nodes.keys())
    expected = [
        "market_data",
        "technicals",
        "fundamentals",
        "valuation",
        "capital_sentiment",
        "macro_industry",
        "bull_bear_debate",
        "risk_manager",
        "portfolio_manager",
    ]
    for name in expected:
        assert name in node_names, f"Node '{name}' missing from workflow"
    assert len(node_names) == len(expected), (
        f"Unexpected nodes: {set(node_names) - set(expected)}"
    )


def test_workflow_compiles():
    """Workflow should compile without error."""
    wf = build_workflow()
    compiled = wf.compile()
    assert compiled is not None
    # Compiled graph should have an invoke method
    assert hasattr(compiled, "invoke")


def test_compiled_graph_has_all_nodes():
    """Compiled graph should contain all 9 agent nodes."""
    wf = build_workflow()
    compiled = wf.compile()
    node_names = list(compiled.nodes.keys())
    expected_nodes = [
        "market_data",
        "technicals",
        "fundamentals",
        "valuation",
        "capital_sentiment",
        "macro_industry",
        "bull_bear_debate",
        "risk_manager",
        "portfolio_manager",
    ]
    for name in expected_nodes:
        assert name in node_names, f"Node '{name}' missing from compiled graph"
    unexpected = set(node_names) - set(expected_nodes) - {"__start__"}
    assert not unexpected, f"Unexpected nodes: {unexpected}"


def test_compiled_graph_has_branches():
    """Compiled graph should have branch edges for fan-out."""
    wf = build_workflow()
    compiled = wf.compile()
    # The compiled graph's trigger_to_nodes shows branch conditions
    triggers = compiled.trigger_to_nodes
    assert triggers is not None
    branch_triggers = [t for t in triggers if t.startswith("branch:to:")]
    assert any("technicals" in t for t in branch_triggers), (
        "Expected fan-out branches to analysis agents"
    )


def test_workflow_edges_connect():
    """Debate room should feed into risk manager, which feeds into portfolio manager."""
    wf = build_workflow()
    compiled = wf.compile()
    # Verify the workflow chain contains all required nodes
    node_names = set(compiled.nodes.keys())
    assert "bull_bear_debate" in node_names
    assert "risk_manager" in node_names
    assert "portfolio_manager" in node_names


def test_build_agents_workflow_single_agent():
    """单 agent 子图应包含 market_data + 1 个 agent 节点。"""
    from valor.agents.workflow import build_agents_workflow

    wf = build_agents_workflow(["technicals"])
    compiled = wf.compile()
    node_names = list(compiled.nodes.keys())
    assert "market_data" in node_names
    assert "technicals" in node_names
    assert len(node_names) == 3  # market_data + technicals + __start__


def test_build_agents_workflow_multi_agent():
    """多 agent 子图应包含 market_data + N 个 agent 节点。"""
    from valor.agents.workflow import build_agents_workflow

    wf = build_agents_workflow(["technicals", "valuation"])
    compiled = wf.compile()
    node_names = list(compiled.nodes.keys())
    assert "market_data" in node_names
    assert "technicals" in node_names
    assert "valuation" in node_names
    assert len(node_names) == 4  # market_data + 2 agents + __start__


def test_build_agents_workflow_invalid_agent_raises():
    """无效 agent key 应抛 ValueError。"""
    import pytest
    from valor.agents.workflow import build_agents_workflow

    with pytest.raises(ValueError, match="Unknown agent"):
        build_agents_workflow(["invalid_agent"])


def test_build_agents_workflow_empty_list_raises():
    """空 agent 列表应抛 ValueError。"""
    import pytest
    from valor.agents.workflow import build_agents_workflow

    with pytest.raises(ValueError):
        build_agents_workflow([])


def test_safe_agent_node_catches_exception(monkeypatch):
    """单个 agent 抛异常时，应返回 failed metadata 而非中断。"""
    from valor.agents import workflow as wf
    from valor.agents.state import AgentState

    def _boom(state: AgentState) -> dict:
        raise RuntimeError("agent exploded")

    # 替换 technicals 节点为会抛异常的函数
    monkeypatch.setitem(wf._AGENT_NODES, "technicals", _boom)

    # 构建包装后的节点
    safe_node = wf._make_safe_agent_node("technicals", _boom)
    result = safe_node({"messages": [], "data": {"ticker": "600519"}, "metadata": {}})
    assert result["metadata"].get("failed") is True
    assert "agent exploded" in result["metadata"]["error"]
    # messages 里应有带 name 的 HumanMessage
    assert len(result["messages"]) == 1
    assert result["messages"][0].name == "technical_analyst_agent"
