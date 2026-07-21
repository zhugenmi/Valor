"""Polish a sub-agent's structured decision into user-friendly markdown.

When single_analysis runs a sub-agent (technicals / fundamentals / ...), the
agent returns a JSON decision dict. Sending that raw JSON to the frontend
renders as a wall of escaped JSON text. This module asks the LLM to rewrite
the dict as a concise Chinese markdown summary before it is streamed out.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from __future__ import annotations

import json
import logging
from typing import Any

from valor.adapters.llm.protocol import Message
from valor.adapters.llm.router import get_llm_provider

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """你是 ValorAgent，A 股投资分析助手。下游分析子 agent 返回了结构化的 JSON 决策结果，请基于此用中文写一段简洁友好的分析摘要给用户。

要求：
- 使用 Markdown 格式（用二级标题、加粗、列表等组织信息）
- 开头一句话总结论：信号方向 + 置信度（如「整体偏多，置信度 50%」）
- 然后展开各子信号的关键理由，保留具体数字和百分比
- 不要罗列原始 JSON 字段名，转换为自然语言（如 "ROE: 6.30%" 写成 "ROE 为 6.30%"）
- 200-400 字之间

严格约束（违反将严重误导用户）：
1. 必须严格直接引用 JSON 中已有的数字和百分比，**严禁自行计算、估算或编造**任何数字。JSON 中没有的数字一律不得出现。
2. **信号方向必须以 JSON 中的 signal 字段为准**，严禁根据数字大小自行推断方向。signal="bullish" 就是看涨，signal="bearish" 就是看跌，signal="neutral" 就是中性——即便你觉得数字关系似乎相反，也必须按 signal 字段写。
3. 如果各子信号的 signal 方向不一致，必须如实说明"子信号方向不一致"，**严禁声称"一致"**。如实在文中分别列出每个子信号的方向。
4. evidence 字段（如有）是权威数据源，引用数字时优先取 evidence 中的值，不得用 reasoning.details 中的字符串自行重新解析。"""

_AGENT_LABELS: dict[str, str] = {
    "technicals": "技术面分析",
    "fundamentals": "基本面分析",
    "valuation": "估值分析",
    "capital_sentiment": "资金情绪分析",
    "macro_industry": "宏观行业分析",
    "bull_bear_debate.bull": "多头论点",
    "bull_bear_debate.bear": "空头论点",
    "bull_bear_debate.verdict": "多空裁决",
    "risk_manager": "风险管理",
    "portfolio_manager": "组合决策",
    "market_data": "市场数据",
}


# Per-agent field hints injected into the user message so the LLM doesn't
# have to guess the semantics of non-obvious fields (e.g. valuation gaps,
# where positive = undervalued, not "price is high").
_AGENT_FIELD_HINTS: dict[str, str] = {
    "valuation": (
        "估值分析字段含义（重要，必须严格遵守）：\n"
        "- signal: 整体估值信号。bullish=低估（看涨），bearish=高估（看跌），neutral=中性\n"
        "- evidence.dcf_gap: DCF 内在价值相对市值的偏差。**正值=内在价值高于市值=低估=看涨；负值=内在价值低于市值=高估=看跌**\n"
        "- evidence.owner_earnings_gap: 所有者收益价值相对市值的偏差，正负含义同上\n"
        "- evidence.valuation_gap: 两种方法的平均偏差，正负含义同上\n"
        "- evidence.dcf_value / owner_earnings_value / market_cap: DCF 内在价值 / 所有者收益企业价值 / 市值（单位：元）\n"
        "- reasoning.dcf_analysis.signal: DCF 子信号\n"
        "- reasoning.owner_earnings_analysis.signal: 所有者收益子信号\n"
        "\n"
        "注意：DCF 和所有者收益两个子信号可能方向相反（一个看涨一个看跌），这是正常情况。"
        "必须如实分别说明每个子信号的方向，严禁强行声称\"一致\"。"
        "整体 signal 是两种方法的综合，可能与任一子信号方向都不同。\n"
    ),
}


def _agent_label(agent_key: str) -> str:
    return _AGENT_LABELS.get(agent_key, agent_key)


def _field_hints(agent_name: str) -> str:
    return _AGENT_FIELD_HINTS.get(agent_name, "")


def _fallback_markdown(agent_name: str, decision: dict[str, Any]) -> str:
    """Pretty-printed JSON fenced as markdown, used when LLM is unavailable."""
    pretty = json.dumps(decision, ensure_ascii=False, indent=2)
    return f"## {_agent_label(agent_name)}\n\n```json\n{pretty}\n```"


async def polish_decision(
    ticker: str,
    agent_name: str,
    decision: dict[str, Any],
) -> str:
    """Rewrite a sub-agent's JSON decision as user-friendly markdown.

    Falls back to a pretty-printed JSON code block if the LLM provider is
    unavailable or the call fails, so the frontend always has something
    to render.
    """
    try:
        provider = get_llm_provider()
    except RuntimeError as exc:
        logger.warning("polish_decision: no LLM provider (%s); returning raw JSON", exc)
        return _fallback_markdown(agent_name, decision)

    hints = _field_hints(agent_name)
    hints_block = f"{hints}\n" if hints else ""
    user_content = (
        f"股票代码：{ticker}\n"
        f"分析维度：{_agent_label(agent_name)}\n\n"
        f"{hints_block}"
        f"子 agent 返回的结构化决策：\n"
        f"{json.dumps(decision, ensure_ascii=False, indent=2)}"
    )
    messages = [
        Message(role="system", content=_SYSTEM_PROMPT),
        Message(role="user", content=user_content),
    ]

    try:
        response = await provider.chat(
            messages=messages,
            temperature=0.3,
            max_tokens=1024,
        )
    except Exception as exc:
        logger.warning("polish_decision LLM call failed: %r; returning raw JSON", exc)
        return _fallback_markdown(agent_name, decision)

    text = response.strip()
    if not text:
        return _fallback_markdown(agent_name, decision)
    return text


__all__ = ["polish_decision"]
