"""LangGraph workflow for Valor investment analysis.

Defines the agent orchestration graph:
  1. market_data_agent  -> collect price/financial data
  2. 5 dimension agents (parallel) -> technicals, fundamentals, valuation,
     capital_sentiment, macro_industry
  3. bull_bear_debate_agent -> synthesizes bull/bear arguments
  4. risk_manager_agent -> risk assessment
  5. portfolio_manager_agent -> final trading decision

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

import operator
from typing import Annotated, Any, Callable, Dict, Iterator, List, Optional, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import END, StateGraph

from valor.agents.bull_bear_debate import bull_bear_debate_agent
from valor.agents.capital_sentiment import capital_sentiment_agent
from valor.agents.fundamentals import fundamentals_agent
from valor.agents.macro_industry import macro_industry_agent
from valor.agents.market_data import market_data_agent
from valor.agents.portfolio_manager import portfolio_management_agent
from valor.agents.risk_manager import risk_management_agent
from valor.agents.state import AgentState
from valor.agents.technicals import technical_analyst_agent
from valor.agents.valuation import valuation_agent


# ---------------------------------------------------------------------------
# Graph state
# ---------------------------------------------------------------------------

def _deep_merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """Recursive dict merge — merges nested dicts instead of overwriting."""
    result = a.copy()
    for key, b_val in b.items():
        if key in result and isinstance(result[key], dict) and isinstance(b_val, dict):
            result[key] = _deep_merge(result[key], b_val)
        else:
            result[key] = b_val
    return result


class GraphState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    data: Annotated[Dict[str, Any], _deep_merge]
    metadata: Annotated[Dict[str, Any], _deep_merge]


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------

def _run_market_data(state: GraphState) -> Dict[str, Any]:
    """Collect market data first (sequential gate)."""
    return market_data_agent(AgentState(
        messages=state["messages"],
        data=state.get("data", {}),
        metadata=state.get("metadata", {}),
    ))


def _run_technicals(state: GraphState) -> Dict[str, Any]:
    return technical_analyst_agent(AgentState(
        messages=state["messages"],
        data=state.get("data", {}),
        metadata=state.get("metadata", {}),
    ))


def _run_fundamentals(state: GraphState) -> Dict[str, Any]:
    return fundamentals_agent(AgentState(
        messages=state["messages"],
        data=state.get("data", {}),
        metadata=state.get("metadata", {}),
    ))


def _run_valuation(state: GraphState) -> Dict[str, Any]:
    return valuation_agent(AgentState(
        messages=state["messages"],
        data=state.get("data", {}),
        metadata=state.get("metadata", {}),
    ))


def _run_capital_sentiment(state: GraphState) -> Dict[str, Any]:
    return capital_sentiment_agent(AgentState(
        messages=state["messages"],
        data=state.get("data", {}),
        metadata=state.get("metadata", {}),
    ))


def _run_macro_industry(state: GraphState) -> Dict[str, Any]:
    return macro_industry_agent(AgentState(
        messages=state["messages"],
        data=state.get("data", {}),
        metadata=state.get("metadata", {}),
    ))


def _run_bull_bear_debate(state: GraphState, stage_callback=None) -> Dict[str, Any]:
    return bull_bear_debate_agent(
        AgentState(
            messages=state["messages"],
            data=state.get("data", {}),
            metadata=state.get("metadata", {}),
        ),
        stage_callback=stage_callback,
    )


def _run_risk_manager(state: GraphState) -> Dict[str, Any]:
    return risk_management_agent(AgentState(
        messages=state["messages"],
        data=state.get("data", {}),
        metadata=state.get("metadata", {}),
    ))


def _run_portfolio_manager(state: GraphState) -> Dict[str, Any]:
    return portfolio_management_agent(AgentState(
        messages=state["messages"],
        data=state.get("data", {}),
        metadata=state.get("metadata", {}),
    ))


# ---------------------------------------------------------------------------
# Build graph
# ---------------------------------------------------------------------------

def build_workflow(
    stage_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
) -> StateGraph:
    """Build the LangGraph investment analysis workflow (9 nodes).

    Args:
        stage_callback: Optional callable invoked as
            ``stage_callback(sub_key, payload)`` after each bull_bear_debate
            sub-stage (bull/bear/verdict) completes. When provided, the SSE
            layer uses it to stream sub-events incrementally instead of
            waiting for the whole bull_bear_debate node to finish.

    Returns:
        A compiled StateGraph ready for invocation.
    """
    workflow = StateGraph(GraphState)

    # Register nodes
    workflow.add_node("market_data", _run_market_data)
    workflow.add_node("technicals", _run_technicals)
    workflow.add_node("fundamentals", _run_fundamentals)
    workflow.add_node("valuation", _run_valuation)
    workflow.add_node("capital_sentiment", _run_capital_sentiment)
    workflow.add_node("macro_industry", _run_macro_industry)
    workflow.add_node(
        "bull_bear_debate",
        lambda state: _run_bull_bear_debate(state, stage_callback=stage_callback),
    )
    workflow.add_node("risk_manager", _run_risk_manager)
    workflow.add_node("portfolio_manager", _run_portfolio_manager)

    # Sequential gate: data collection first
    workflow.set_entry_point("market_data")

    # Fan out from data to all 5 dimension agents (parallel)
    for agent in ["technicals", "fundamentals", "valuation", "capital_sentiment", "macro_industry"]:
        workflow.add_edge("market_data", agent)

    # All 5 dimension agents converge to bull_bear_debate (fan-in)
    for agent in ["technicals", "fundamentals", "valuation", "capital_sentiment", "macro_industry"]:
        workflow.add_edge(agent, "bull_bear_debate")

    # Debate -> risk -> portfolio -> END
    workflow.add_edge("bull_bear_debate", "risk_manager")
    workflow.add_edge("risk_manager", "portfolio_manager")
    workflow.add_edge("portfolio_manager", END)

    return workflow


# ---------------------------------------------------------------------------
# Single-agent workflow (market_data + one analysis agent)
# ---------------------------------------------------------------------------

_AGENT_NODES: Dict[str, Any] = {
    "technicals": _run_technicals,
    "fundamentals": _run_fundamentals,
    "valuation": _run_valuation,
    "capital_sentiment": _run_capital_sentiment,
    "macro_industry": _run_macro_industry,
}

_AGENT_MESSAGE_NAMES: Dict[str, str] = {
    "technicals": "technical_analyst_agent",
    "fundamentals": "fundamentals_agent",
    "valuation": "valuation_agent",
    "capital_sentiment": "capital_sentiment_agent",
    "macro_industry": "macro_industry_agent",
}


def build_agents_workflow(agent_names: list[str]) -> StateGraph:
    """Build a workflow that runs market_data + N analysis agents in parallel.

    Args:
        agent_names: 1-N keys from ``_AGENT_NODES`` (e.g. ["technicals", "valuation"]).

    Returns:
        An uncompiled StateGraph: ``market_data -> [agent1, agent2, ...] -> END``
        (fan-out parallel execution).
    """
    if not agent_names:
        raise ValueError("agent_names must not be empty")
    for name in agent_names:
        if name not in _AGENT_NODES:
            raise ValueError(
                f"Unknown agent '{name}'. Valid: {sorted(_AGENT_NODES.keys())}"
            )

    workflow = StateGraph(GraphState)
    workflow.add_node("market_data", _run_market_data)
    for name in agent_names:
        workflow.add_node(name, _AGENT_NODES[name])
    workflow.set_entry_point("market_data")
    for name in agent_names:
        workflow.add_edge("market_data", name)  # fan-out parallel
        workflow.add_edge(name, END)
    return workflow


def agent_message_name(agent_key: str) -> str:
    """Return the HumanMessage.name attribute produced by the given agent key."""
    return _AGENT_MESSAGE_NAMES[agent_key]


# ---------------------------------------------------------------------------
# Convenience runner
# ---------------------------------------------------------------------------

def _build_initial_state(
    ticker: str,
    start_date: str | None = None,
    end_date: str | None = None,
    portfolio: Dict[str, Any] | None = None,
    show_reasoning: bool = False,
    model: str = "openai",
    **kwargs: Any,
) -> Dict[str, Any]:
    """Build the initial GraphState for analysis workflows.

    Shared by run_analysis() and stream_analysis() to ensure identical state shape.

    Args:
        ticker: A-share ticker, e.g. "600519"
        start_date: Analysis start date (YYYY-MM-DD)
        end_date: Analysis end date (YYYY-MM-DD)
        portfolio: Portfolio dict with "cash" and "stock" keys
        show_reasoning: Whether to include reasoning in output
        model: LLM model name
        **kwargs: Additional metadata fields

    Returns:
        GraphState-compatible dict with messages/data/metadata keys.
    """
    if portfolio is None:
        portfolio = {"cash": 100000.0, "stock": 0}

    return {
        "messages": [
            HumanMessage(
                content=f"Analyze ticker {ticker} from {start_date or 'auto'} to {end_date or 'auto'}",
                name="user",
            )
        ],
        "data": {
            "ticker": ticker,
            "start_date": start_date or "",
            "end_date": end_date or "",
            "portfolio": portfolio,
        },
        "metadata": {
            "show_reasoning": show_reasoning,
            "model": model,
            **kwargs,
        },
    }


def run_analysis(
    ticker: str,
    start_date: str | None = None,
    end_date: str | None = None,
    portfolio: Dict[str, Any] | None = None,
    show_reasoning: bool = False,
    model: str = "openai",
    **kwargs: Any,
) -> Dict[str, Any]:
    """Run the full analysis workflow for a ticker (blocking).

    Args:
        ticker: A-share ticker, e.g. "600519"
        start_date: Analysis start date (YYYY-MM-DD)
        end_date: Analysis end date (YYYY-MM-DD)
        portfolio: Portfolio dict with "cash" and "stock" keys
        show_reasoning: Whether to include reasoning in output
        model: LLM model name
        **kwargs: Additional state metadata

    Returns:
        Final state dict from the workflow.
    """
    initial_state = _build_initial_state(
        ticker, start_date, end_date, portfolio, show_reasoning, model, **kwargs
    )
    app = build_workflow()
    compiled = app.compile()
    result = compiled.invoke(initial_state)
    return dict(result)


def stream_analysis(
    ticker: str,
    start_date: str | None = None,
    end_date: str | None = None,
    portfolio: Dict[str, Any] | None = None,
    show_reasoning: bool = False,
    model: str = "openai",
    stage_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    **kwargs: Any,
) -> Iterator[Dict[str, Any]]:
    """Stream the analysis workflow for a ticker, yielding state after each node.

    Uses LangGraph's compiled.stream() to emit incremental state updates.
    Each yielded chunk has format {node_name: state_delta} where state_delta
    is the reducer-merged output of that node.

    Args:
        ticker: A-share ticker, e.g. "600519"
        start_date: Analysis start date (YYYY-MM-DD)
        end_date: Analysis end date (YYYY-MM-DD)
        portfolio: Portfolio dict with "cash" and "stock" keys
        show_reasoning: Whether to include reasoning in output
        model: LLM model name
        stage_callback: Optional callable for streaming bull_bear_debate
            sub-stages. Invoked as ``stage_callback(sub_key, payload)`` after
            each sub-stage (bull/bear/verdict) completes, so the SSE layer
            can emit sub-events incrementally.
        **kwargs: Additional state metadata

    Yields:
        dict: {node_name: state_delta} chunks from LangGraph stream.
    """
    initial_state = _build_initial_state(
        ticker, start_date, end_date, portfolio, show_reasoning, model, **kwargs
    )
    app = build_workflow(stage_callback=stage_callback)
    compiled = app.compile()
    for chunk in compiled.stream(initial_state):
        yield chunk


def run_agents(
    ticker: str,
    agent_names: list[str],
    start_date: str | None = None,
    end_date: str | None = None,
    show_reasoning: bool = False,
    model: str = "openai",
    **kwargs: Any,
) -> Dict[str, Any]:
    """Run market_data + N analysis agents in parallel for a ticker.

    Args:
        ticker: A-share ticker, e.g. "600519"
        agent_names: 1-N keys from ``_AGENT_NODES`` (e.g. ["technicals", "valuation"])
        start_date: Analysis start date (YYYY-MM-DD)
        end_date: Analysis end date (YYYY-MM-DD)
        show_reasoning: Whether to include reasoning in output
        model: LLM model name
        **kwargs: Additional state metadata

    Returns:
        Final state dict from the workflow. ``state["messages"]`` contains
        HumanMessages from each agent, identifiable by ``msg.name``.
    """
    initial_state: GraphState = {
        "messages": [
            HumanMessage(
                content=f"Analyze ticker {ticker} from {start_date or 'auto'} to {end_date or 'auto'}",
                name="user",
            )
        ],
        "data": {
            "ticker": ticker,
            "start_date": start_date or "",
            "end_date": end_date or "",
            "portfolio": {"cash": 100000.0, "stock": 0},
        },
        "metadata": {
            "show_reasoning": show_reasoning,
            "model": model,
            **kwargs,
        },
    }

    app = build_agents_workflow(agent_names)
    compiled = app.compile()

    result = compiled.invoke(initial_state)
    return dict(result)
