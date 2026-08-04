"""Fundamentals agent - industry-cluster-aware configuration-driven evaluation.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
import json

from langchain_core.messages import HumanMessage

from valor.agents._kb_helpers import build_correction_section, build_kb_section, extract_citations
from valor.agents.state import AgentState, show_agent_reasoning, show_workflow_status
from valor.utils.logging_config import setup_logger
from valor.utils.api_utils import agent_endpoint
from valor.strategy.industry_clusters import IndustryCluster
from valor.strategy.industry_clusters import INDUSTRY_CLUSTERS
from valor.strategy.metric_evaluators import evaluate_dimension

logger = setup_logger("fundamentals_agent")


# Fields whose raw value is a decimal fraction (0.04 = 4%) and should render
# as a percentage. All other fields render as their raw numeric value (ratios,
# counts, per-share amounts). Keeping this as an explicit set avoids guessing
# from label text, which is ambiguous (e.g. "拨备覆盖率" is a multiple, not a
# percent, despite the "率" character).
_PERCENT_FIELDS: frozenset[str] = frozenset({
    # profitability
    "return_on_equity", "net_margin", "operating_margin", "gross_margin",
    "net_interest_margin",
    # growth
    "revenue_growth", "earnings_growth", "book_value_growth",
    # financial health
    "non_performing_loan_ratio", "core_tier1_capital_ratio",
    "r_and_d_capitalization_rate", "sales_expense_ratio",
    "receivable_to_revenue", "adj_debt_to_asset", "debt_to_equity",
    "capex_to_ocf", "ocf_to_net_profit",
    # valuation
    "pb_percentile_5y",
    # shareholder return
    "dividend_yield", "payout_ratio",
    # r&d
    "r_and_d_to_revenue",
})


def _fmt_date(val) -> str:
    """格式化日期为 YYYY-MM-DD，处理 Timestamp/str/None。"""
    if val is None:
        return ""
    try:
        import pandas as pd  # noqa: PLC0415
        if not pd.isna(val):
            return pd.Timestamp(val).strftime("%Y-%m-%d")
    except Exception:
        pass
    return str(val)[:10]


def _fmt_value(field: str, value) -> str:
    """格式化指标值为展示字符串。None -> 'N/A'。"""
    if value is None:
        return "N/A"
    try:
        if field in _PERCENT_FIELDS:
            return f"{float(value) * 100:.2f}%"
        if field == "dividend_years":
            return f"{int(value)} 年"
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_threshold(row: dict) -> str:
    """根据 judge 和 threshold 生成人类可读的参考值字符串。"""
    judge = row.get("judge", "")
    if judge in ("trend_up", "trend_down"):
        return row.get("direction", "")
    field = row.get("field", "")
    if judge == "range":
        lo = _fmt_value(field, row.get("threshold_low"))
        hi = _fmt_value(field, row.get("threshold_high"))
        return f"{lo} ~ {hi}"
    thr = row.get("threshold")
    if thr is None:
        return "-"
    thr_str = _fmt_value(field, thr)
    if judge == "threshold_gt":
        return f"≥ {thr_str}"
    if judge == "threshold_lt":
        return f"< {thr_str}"
    return thr_str


def _metric_status(row: dict) -> str:
    """单指标状态：skip / reference / pass / fail。"""
    if row.get("skipped"):
        return "skip"
    if row.get("reference_only"):
        return "reference"
    return "pass" if row.get("passed") else "fail"


_SIGNAL_CN = {"bullish": "看多", "bearish": "看空", "neutral": "中性"}


def _build_market_context(metrics: dict, data: dict) -> dict:
    """组装展示用市场上下文：股价/市值/最新财报期/分红方案。

    这些字段不参与评分，仅供前端展示。
    """
    market_cap = data.get("market_cap") or metrics.get("market_cap") or 0
    latest_div = metrics.get("latest_dividend")
    dividend_summary = None
    if latest_div:
        dividend_summary = {
            "公告日期": _fmt_date(latest_div.get("公告日期")),
            "每10股派息": latest_div.get("派息"),
            "送股": latest_div.get("送股"),
            "转增": latest_div.get("转增"),
            "进度": latest_div.get("进度", ""),
            "除权除息日": _fmt_date(latest_div.get("除权除息日")),
        }
    return {
        "current_price": metrics.get("current_price"),
        "market_cap": market_cap,
        "report_date": metrics.get("report_date", ""),
        "latest_dividend": dividend_summary,
    }


def _build_scoring_table(
    config: IndustryCluster,
    reasoning: dict,
    overall_signal: str,
    confidence: str,
    overall_score: float,
) -> dict:
    """组装多维度打分表格：维度 -> 指标(实际值/参考值/是否通过)。"""
    dim_rows: list[dict] = []
    for dim in config.dimensions:
        dim_result = reasoning[dim.name]
        metric_rows: list[dict] = []
        for m in dim_result["metrics"]:
            field = m.get("field", "")
            metric_rows.append({
                "label": m.get("label", ""),
                "field": field,
                "value": m.get("value"),
                "display_value": _fmt_value(field, m.get("value")),
                "judge": m.get("judge", ""),
                "direction": m.get("direction", ""),
                "threshold": m.get("threshold"),
                "threshold_low": m.get("threshold_low"),
                "threshold_high": m.get("threshold_high"),
                "display_threshold": _fmt_threshold(m),
                "passed": m.get("passed", False),
                "skipped": m.get("skipped", False),
                "reference_only": m.get("reference_only", False),
                "status": _metric_status(m),
                "description": m.get("description", ""),
            })
        dim_rows.append({
            "name": dim.name,
            "label": dim.label,
            "weight": dim.weight,
            "weight_display": f"{round(dim.weight * 100)}%",
            "signal": dim_result["signal"],
            "signal_cn": _SIGNAL_CN.get(dim_result["signal"], ""),
            "rule": dim.rule,
            "metrics": metric_rows,
        })

    counts = {
        "bullish": sum(1 for d in dim_rows if d["signal"] == "bullish"),
        "neutral": sum(1 for d in dim_rows if d["signal"] == "neutral"),
        "bearish": sum(1 for d in dim_rows if d["signal"] == "bearish"),
        "total": len(dim_rows),
    }
    return {
        "cluster_key": config.key,
        "cluster_label": config.label,
        "valuation_method": config.valuation_method,
        "dimensions": dim_rows,
        "overall": {
            "signal": overall_signal,
            "signal_cn": _SIGNAL_CN.get(overall_signal, ""),
            "confidence": confidence,
            "score": round(overall_score, 2),
            "dimension_summary": counts,
        },
    }


def _build_summary(
    config: IndustryCluster,
    reasoning: dict,
    overall_signal: str,
    confidence: str,
    data: dict,
) -> str:
    """生成一段中文综合分析文本，串联行业定位/维度表现/关键指标/结论。"""
    industry = data.get("industry", "") or config.label
    name = data.get("stock_name", "") or data.get("symbol", "")
    parts: list[str] = []

    parts.append(
        f"{name}归属于「{industry}」，按「{config.label}」集群评分框架评估，"
        f"估值方法以{config.valuation_method}为主。"
    )

    dim_strs: list[str] = []
    for dim in config.dimensions:
        r = reasoning[dim.name]
        dim_strs.append(
            f"{dim.label}({round(dim.weight * 100)}%权重){_SIGNAL_CN.get(r['signal'], '')}"
        )
    parts.append("各维度评分：" + "、".join(dim_strs) + "。")

    # 亮点与风险：挑出通过的关键指标和未通过的关键指标
    highlights: list[str] = []
    risks: list[str] = []
    for dim in config.dimensions:
        for m in reasoning[dim.name]["metrics"]:
            if m.get("skipped") or m.get("reference_only"):
                continue
            label = m.get("label", "")
            val = _fmt_value(m.get("field", ""), m.get("value"))
            thr = _fmt_threshold(m)
            if m.get("passed"):
                highlights.append(f"{label}={val}（参考值{thr}）")
            else:
                risks.append(f"{label}={val}（参考值{thr}）")
    if highlights:
        parts.append("亮点指标：" + "、".join(highlights[:4]) + "。")
    if risks:
        parts.append("风险指标：" + "、".join(risks[:4]) + "。")

    parts.append(
        f"综合信号{_SIGNAL_CN.get(overall_signal, '')}，置信度{confidence}。"
    )
    return "".join(parts)


@agent_endpoint("fundamentals", "基本面分析师，按行业集群定制评分")
def fundamentals_agent(state: AgentState):
    """Configuration-driven fundamental analysis by industry cluster."""
    show_workflow_status("Fundamentals Analyst")
    show_reasoning = state["metadata"]["show_reasoning"]
    data = state["data"]
    citations = []
    kb_ctx = state["data"].get("kb_context", {}).get("fundamentals", {})
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
    confidence_str = f"{round(confidence * 100)}%"

    evidence = {k: float(v) for k, v in metrics.items() if isinstance(v, (int, float))}

    ticker = data.get("ticker") or data.get("symbol") or ""
    report_period = data.get("end_date") or metrics.get("report_date") or ""
    correction_section = build_correction_section(ticker, report_period, kb_ctx)
    corrections_list = []
    if correction_section:
        try:
            from valor.knowledge_base.corrector import get_corrections as _get_corrections
            corrections_list = [c.model_dump() for c in _get_corrections(ticker, report_period)]
        except Exception:
            pass

    message_content = {
        "signal": overall_signal,
        "confidence": confidence_str,
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
        "market_context": _build_market_context(metrics, data),
        "scoring_table": _build_scoring_table(
            config, reasoning, overall_signal, confidence_str, overall
        ),
        "summary": _build_summary(config, reasoning, overall_signal, confidence_str, data),
        "data_corrections": correction_section,
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
        "metadata": {
            **state["metadata"],
            "fundamentals_citations": citations,
            "fundamentals_corrections": corrections_list,
        },
    }