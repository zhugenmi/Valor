"""Fundamentals agent - industry-cluster-aware configuration-driven evaluation.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
import json

from langchain_core.messages import HumanMessage

from valor.agents.state import AgentState, show_agent_reasoning, show_workflow_status
from valor.utils.logging_config import setup_logger
from valor.utils.api_utils import agent_endpoint
from valor.strategy.industry_clusters import INDUSTRY_CLUSTERS
from valor.strategy.metric_evaluators import evaluate_dimension

logger = setup_logger("fundamentals_agent")


@agent_endpoint("fundamentals", "基本面分析师，按行业集群定制评分")
def fundamentals_agent(state: AgentState):
    """Configuration-driven fundamental analysis by industry cluster."""
    show_workflow_status("Fundamentals Analyst")
    show_reasoning = state["metadata"]["show_reasoning"]
    data = state["data"]
    metrics = data.get("financial_metrics", [{}])[0] or {}
    cluster_key = data.get("cluster", "conglomerate")
    config = INDUSTRY_CLUSTERS.get(cluster_key, INDUSTRY_CLUSTERS["conglomerate"])

    reasoning = {}
    weighted_scores: list[tuple[float, int]] = []
    _score_map = {"bullish": 1, "bearish": -1, "neutral": 0}

    for dim in config.dimensions:
        dim_signal, dim_details, metric_results = evaluate_dimension(dim, metrics)
        reasoning[dim.name] = {
            "signal": dim_signal,
            "weight": dim.weight,
            "details": dim_details,
            "metrics": metric_results,
        }
        weighted_scores.append((dim.weight, _score_map[dim_signal]))

    overall = sum(w * s for w, s in weighted_scores)
    if overall > 0.2:
        overall_signal = "bullish"
    elif overall < -0.2:
        overall_signal = "bearish"
    else:
        overall_signal = "neutral"
    confidence = min(abs(overall), 1.0)

    evidence = {k: float(v) for k, v in metrics.items() if isinstance(v, (int, float))}

    message_content = {
        "signal": overall_signal,
        "confidence": f"{round(confidence * 100)}%",
        "reasoning": reasoning,
        "risk_flags": [],
        "evidence": evidence,
        "industry_profile": {
            "cluster": config.key,
            "cluster_label": config.label,
            "industry": data.get("industry", ""),
            "valuation_method": config.valuation_method,
            "notes": config.notes,
        },
    }

    message = HumanMessage(
        content=json.dumps(message_content, ensure_ascii=False),
        name="fundamentals_agent",
    )

    if show_reasoning:
        show_agent_reasoning(message_content, "Fundamental Analysis Agent")
        state["metadata"]["agent_reasoning"] = message_content

    show_workflow_status("Fundamentals Analyst", "completed")
    return {
        "messages": [message],
        "data": {**data, "fundamental_analysis": message_content},
        "metadata": state["metadata"],
    }