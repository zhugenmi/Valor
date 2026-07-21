"""LLM-based intent classification for user messages.

Routes incoming queries to one of:
  - chat: conversational / non-stock questions
  - full_analysis: complete stock analysis workflow
  - single_analysis: one specific aspect (technicals / fundamentals / ...)

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal

from loguru import logger

from valor.adapters.llm.protocol import Message
from valor.adapters.llm.router import get_llm_provider

IntentType = Literal["chat", "full_analysis", "single_analysis"]

VALID_AGENTS = frozenset({
    "technicals",
    "fundamentals",
    "valuation",
    "capital_sentiment",
    "macro_industry",
})

_SYSTEM_PROMPT = """你是 ValorAgent，一个 A 股投资分析助手的主编排器。分析用户输入，判断意图并提取信息。

只输出JSON，不要任何额外文字或markdown标记。JSON格式：
{"intent": "chat|full_analysis|single_analysis", "ticker": "6位股票代码或null", "agents": ["technicals","valuation",...], "reply": "chat意图时的回复，否则null"}

意图规则：
- chat：闲聊、问候、或非股票分析的问题（如"hi"、"你好"、"你是谁"、"谢谢"）。reply字段给出友好的中文回复。
- full_analysis：用户要求全面分析某只股票（如"分析600519"、"贵州茅台值得买吗"、"600519怎么样"、"诊断股票600519"）。ticker提取6位A股代码。agents为空数组。
- single_analysis：用户只问某一方面或多方面组合。agents字段返回1-N个维度：
  - technicals：技术指标、K线、走势、买卖点
  - fundamentals：基本面、财报、盈利能力
  - valuation：估值、DCF、内在价值
  - capital_sentiment：资金面、情绪、舆情、北向资金、龙虎榜
  - macro_industry：宏观环境、行业前景、政策影响、宏观新闻

示例：
输入"hi" -> {"intent":"chat","ticker":null,"agents":[],"reply":"你好！请提供股票代码（如600519），我可以帮您分析。"}
输入"分析600519" -> {"intent":"full_analysis","ticker":"600519","agents":[],"reply":null}
输入"600519的技术指标怎么样" -> {"intent":"single_analysis","ticker":"600519","agents":["technicals"],"reply":null}
输入"五粮液技术面和估值" -> {"intent":"single_analysis","ticker":"000858","agents":["technicals","valuation"],"reply":null}
输入"600519基本面技术面估值" -> {"intent":"single_analysis","ticker":"600519","agents":["fundamentals","technicals","valuation"],"reply":null}
输入"最近宏观新闻" -> {"intent":"single_analysis","ticker":null,"agents":["macro_industry"],"reply":null}
输入"诊断股票600519" -> {"intent":"full_analysis","ticker":"600519","agents":[],"reply":null}"""

_TICKER_RE = re.compile(r"(?<!\d)[0-6]\d{5}(?!\d)")

_DIMENSION_KEYWORDS: list[tuple[str, str]] = [
    ("technicals", r"技术面|技术指标|K线|走势|买卖点"),
    ("fundamentals", r"基本面|财报|盈利能力|财务"),
    ("valuation", r"估值|DCF|内在价值"),
    ("capital_sentiment", r"资金面|情绪|舆情|北向资金|龙虎榜"),
    ("macro_industry", r"宏观|行业|政策|宏观新闻"),
]

_DEFAULT_CHAT_REPLY = "您好，请提供股票代码（如600519）以进行分析。"


def _fallback(query: str) -> IntentResult:
    """Regex-based fallback when the LLM classifier is unavailable."""
    m = _TICKER_RE.search(query)
    ticker = m.group(0) if m else None

    agents: list[str] = []
    for agent_key, pattern in _DIMENSION_KEYWORDS:
        if re.search(pattern, query):
            agents.append(agent_key)

    if ticker and agents:
        return IntentResult(intent="single_analysis", ticker=ticker, agents=agents)
    if ticker:
        return IntentResult(intent="full_analysis", ticker=ticker, agents=[])
    if agents:
        # 无 ticker 但有维度（如纯宏观问题）
        return IntentResult(intent="single_analysis", ticker=None, agents=agents)
    return IntentResult(intent="chat", reply=_DEFAULT_CHAT_REPLY)


@dataclass
class IntentResult:
    """Outcome of intent classification."""

    intent: IntentType
    ticker: str | None = None
    agents: list[str] = None  # type: ignore[assignment]  # 默认值在 __post_init__ 设置
    reply: str | None = None

    def __post_init__(self) -> None:
        if self.agents is None:
            self.agents = []

    @property
    def agent(self) -> str | None:
        """Backward compat: 返回首个 agent 或 None。"""
        return self.agents[0] if self.agents else None


def _coerce(raw: dict) -> IntentResult:
    """Validate and normalize the LLM's JSON output."""
    intent = raw.get("intent", "chat")
    if intent not in ("chat", "full_analysis", "single_analysis"):
        intent = "chat"

    ticker = raw.get("ticker")
    if ticker is not None:
        ticker = str(ticker).strip()
        if not _TICKER_RE.fullmatch(ticker):
            ticker = None

    # 支持 LLM 返回 agents 数组或单个 agent 字符串（向后兼容）
    raw_agents = raw.get("agents")
    if raw_agents is None and raw.get("agent") is not None:
        raw_agents = [raw.get("agent")]
    if not isinstance(raw_agents, list):
        raw_agents = []
    agents = [a for a in raw_agents if a in VALID_AGENTS]

    if intent == "single_analysis" and not agents:
        intent = "full_analysis"

    if intent == "full_analysis" and ticker is None:
        return IntentResult(intent="chat", reply=_DEFAULT_CHAT_REPLY)
    if intent == "single_analysis" and ticker is None and "macro_industry" not in agents:
        return IntentResult(intent="chat", reply=_DEFAULT_CHAT_REPLY)

    reply = raw.get("reply") if intent == "chat" else None
    if intent == "chat" and not reply:
        reply = _DEFAULT_CHAT_REPLY

    return IntentResult(intent=intent, ticker=ticker, agents=agents, reply=reply)


async def classify_intent(query: str) -> IntentResult:
    """Classify a user message into chat / full_analysis / single_analysis.

    Falls back to regex ticker extraction if the LLM call fails or returns
    malformed JSON, so the server stays functional even when the LLM is down.
    """
    if not query or not query.strip():
        return IntentResult(intent="chat", reply=_DEFAULT_CHAT_REPLY)

    try:
        provider = get_llm_provider()
    except RuntimeError as exc:
        logger.warning(f"Intent classifier: no LLM provider ({exc}); using fallback")
        return _fallback(query)

    messages = [
        Message(role="system", content=_SYSTEM_PROMPT),
        Message(role="user", content=query),
    ]

    try:
        response = await provider.chat(
            messages=messages,
            temperature=0.0,
            max_tokens=256,
        )
    except Exception as exc:
        logger.warning(f"Intent classifier LLM call failed: {exc!r}; using fallback")
        return _fallback(query)

    try:
        parsed = json.loads(response)
        if not isinstance(parsed, dict):
            raise ValueError("classifier response is not a JSON object")
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning(f"Intent classifier returned malformed JSON: {exc}; using fallback")
        return _fallback(query)

    return _coerce(parsed)


__all__ = ["IntentResult", "IntentType", "VALID_AGENTS", "classify_intent"]
