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

_SYSTEM_PROMPT = """你是一个意图分类器，用于股票分析助手。分析用户输入，判断意图并提取信息。

只输出JSON，不要任何额外文字或markdown标记。JSON格式：
{"intent": "chat|full_analysis|single_analysis", "ticker": "6位股票代码或null", "agent": "technicals|fundamentals|valuation|capital_sentiment|macro_industry或null", "reply": "chat意图时的回复，否则null"}

意图规则：
- chat：闲聊、问候、或非股票分析的问题（如"hi"、"你好"、"你是谁"、"谢谢"）。reply字段给出友好的中文回复。
- full_analysis：用户要求全面分析某只股票（如"分析600519"、"贵州茅台值得买吗"、"600519怎么样"、"诊断股票600519"）。ticker提取6位A股代码。
- single_analysis：用户只问某一方面：
  - technicals：技术指标、K线、走势、买卖点（如"600519的技术指标"）
  - fundamentals：基本面、财报、盈利能力（如"600519的财报"）
  - valuation：估值、DCF、内在价值（如"600519估值高吗"）
  - capital_sentiment：资金面、情绪、舆情、北向资金、龙虎榜（如"600519最近舆情"、"600519资金流"）
  - macro_industry：宏观环境、行业前景、政策影响、宏观新闻（如"600519的宏观环境"、"最近宏观新闻"）

示例：
输入"hi" -> {"intent":"chat","ticker":null,"agent":null,"reply":"你好！请提供股票代码（如600519），我可以帮您分析。"}
输入"分析600519" -> {"intent":"full_analysis","ticker":"600519","agent":null,"reply":null}
输入"600519的技术指标怎么样" -> {"intent":"single_analysis","ticker":"600519","agent":"technicals","reply":null}
输入"看看茅台的估值" -> {"intent":"single_analysis","ticker":"600519","agent":"valuation","reply":null}
输入"最近宏观新闻" -> {"intent":"single_analysis","ticker":null,"agent":"macro_industry","reply":null}
输入"600519资金面怎么样" -> {"intent":"single_analysis","ticker":"600519","agent":"capital_sentiment","reply":null}
输入"诊断股票600519" -> {"intent":"full_analysis","ticker":"600519","agent":null,"reply":null}"""

_TICKER_RE = re.compile(r"(?<!\d)[0-6]\d{5}(?!\d)")

_DEFAULT_CHAT_REPLY = "您好，请提供股票代码（如600519）以进行分析。"


@dataclass
class IntentResult:
    """Outcome of intent classification."""

    intent: IntentType
    ticker: str | None = None
    agent: str | None = None
    reply: str | None = None


def _fallback(query: str) -> IntentResult:
    """Regex-based fallback when the LLM classifier is unavailable."""
    m = _TICKER_RE.search(query)
    if m:
        return IntentResult(intent="full_analysis", ticker=m.group(0))
    return IntentResult(intent="chat", reply=_DEFAULT_CHAT_REPLY)


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

    agent = raw.get("agent")
    if agent not in VALID_AGENTS:
        agent = None

    if intent == "single_analysis" and agent is None:
        intent = "full_analysis"

    if intent == "full_analysis" and ticker is None:
        return IntentResult(intent="chat", reply=_DEFAULT_CHAT_REPLY)
    if intent == "single_analysis" and ticker is None and agent != "macro_industry":
        return IntentResult(intent="chat", reply=_DEFAULT_CHAT_REPLY)

    reply = raw.get("reply") if intent == "chat" else None
    if intent == "chat" and not reply:
        reply = _DEFAULT_CHAT_REPLY

    return IntentResult(intent=intent, ticker=ticker, agent=agent, reply=reply)


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
