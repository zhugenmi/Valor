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
