"""News query builder - builds search queries for A-Share news retrieval.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from __future__ import annotations

import os
from typing import Optional

from valor.tools.openrouter_config import get_chat_completion
from valor.tools.stock_basic import get_stock_name
from valor.utils.api_utils import log_llm_interaction
from valor.utils.prompt_loader import format_prompt, load_prompt


def _is_chinese(text: str) -> bool:
    for char in text:
        if "\u4e00" <= char <= "\u9fff":
            return True
    return False


def _build_tavily_query(
    symbol: str,
    agent_name: Optional[str],
    company_name: Optional[str] = None,
) -> str:
    if not company_name:
        company_name = get_stock_name(symbol)

    if agent_name == "macro_industry_agent" and symbol in {"000300", "沪深300", "CSI300"}:
        return (
            "帮我搜索最近一周沪深300与A股市场宏观新闻，重点关注央行政策、证监会监管、"
            "流动性、北向资金、风险偏好、指数波动；同时关注海外最重要宏观事件，"
            "包括美联储利率、美国通胀与非农、地缘政治、原油与大宗商品波动对A股的影响"
        )

    if agent_name == "macro_industry_agent":
        if company_name:
            return f"帮我搜索最近一周{company_name}（{symbol}）相关的行业动态、政策变化与宏观研报"
        return f"帮我搜索最近一周{symbol}相关的行业动态、政策变化与宏观研报"

    if agent_name == "capital_sentiment_agent":
        if company_name:
            return f"帮我搜索最近一周{company_name}（{symbol}）的新闻、公告、业绩和订单信息"
        return f"帮我搜索最近一周{symbol}的新闻、公告、业绩和订单信息"

    if agent_name == "market_snapshot":
        if company_name:
            return f"帮我搜索最近一周{company_name}（{symbol}）的资金流、龙虎榜、机构动向和成交信息"
        return f"帮我搜索最近一周{symbol}的资金流、龙虎榜、机构动向和成交信息"

    if agent_name == "capital_flow_agent":
        if company_name:
            return f"帮我搜索最近一周{company_name}（{symbol}）的资金流、龙虎榜、机构动向和成交信息"
        return f"帮我搜索最近一周{symbol}的资金流、龙虎榜、机构动向和成交信息"

    if company_name:
        return f"帮我搜索最近一周{company_name}（{symbol}）的股票财经新闻"
    return f"帮我搜索最近一周{symbol}的股票财经新闻"


def _build_enhanced_query(
    symbol: str,
    agent_name: Optional[str],
    company_name: Optional[str] = None,
) -> str:
    base_query = _build_tavily_query(symbol, agent_name, company_name)

    english_names = {
        "比亚迪": "BYD",
        "宁德时代": "CATL",
        "贵州茅台": "Moutai",
        "中国平安": "Ping An",
        "招商银行": "CMB China Merchants Bank",
        "美的集团": "Midea",
        "格力电器": "Gree",
        "海尔智家": "Haier",
        "隆基绿能": "LONGi",
        "通威股份": "Tongwei",
        "阳光电源": "Sungrow",
        "中芯国际": "SMIC",
        "腾讯控股": "Tencent",
        "阿里巴巴": "Alibaba",
        "京东": "JD.com",
        "拼多多": "PDD",
        "美团": "Meituan",
        "字节跳动": "ByteDance",
        "小米": "Xiaomi",
        "华为": "Huawei",
        "蔚来": "NIO",
        "小鹏": "XPeng",
        "理想": "Li Auto",
    }

    if company_name and company_name in english_names:
        return f"{base_query} {english_names[company_name]}"
    return base_query


def _remove_advanced_operators(query: str) -> str:
    for op in ["after:", "before:", "site:"]:
        query = query.replace(op, "")
    return " ".join(query.split())


def _llm_query(
    symbol: str,
    agent_name: Optional[str],
    trace_state: Optional[dict],
) -> Optional[str]:
    system_prompt = load_prompt("prompts/news_query_builder/system.md")
    if _is_chinese(symbol):
        user_prompt = format_prompt(
            "prompts/news_query_builder/user.md",
            symbol=symbol,
            agent_name=agent_name or "unknown",
            date="today",
        )
    else:
        user_prompt = (
            f"Generate a concise news search query for stock {symbol}, "
            f"agent: {agent_name or 'unknown'}. Return only keywords."
        )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        if trace_state:
            result = log_llm_interaction(trace_state)(get_chat_completion)(messages)
        else:
            result = get_chat_completion(messages)
        if result:
            return _remove_advanced_operators(str(result).strip())
    except Exception:
        pass
    return None


def build_news_query(
    symbol: str,
    *,
    date: str | None = None,
    agent_name: str | None = None,
    trace_state: dict | None = None,
    search_engine: str = "tavily",
) -> str:
    """Build an optimized news search query for a stock."""
    company_name = None
    if agent_name != "macro_industry_agent" and symbol not in {"000300", "沪深300", "CSI300"}:
        company_name = get_stock_name(symbol)

    mode = (os.getenv("NEWS_QUERY_MODE", "rule") or "rule").lower()
    if mode == "llm":
        query = _llm_query(symbol, agent_name, trace_state)
        if query:
            return query
    return _build_enhanced_query(symbol, agent_name, company_name)


def build_search_query(symbol: str, date: str | None = None) -> str:
    """Legacy entry point."""
    return build_news_query(symbol, date=date)
