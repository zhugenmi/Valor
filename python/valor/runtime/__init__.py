"""Agent Runtime: Supervisor + Tools + Specialist Agents.

Phase 3 of ADR-0001. Routes user queries through a Supervisor LLM that
decides at runtime which Tools to call (kb_search, get_stock_data,
run_full_analysis, run_single_agent). Existing 9-node LangGraph workflow
is wrapped as a Tool; KB retrieval and data adapters are wrapped as Tools.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from valor.runtime.main import run_agent_runtime

__all__ = ["run_agent_runtime"]