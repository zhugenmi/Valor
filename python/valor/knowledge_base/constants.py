"""Constants for knowledge base: agent profiles, chunk strategies, vintage rules.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ChunkStrategy:
    """Chunking strategy for a document type."""
    name: str
    chunk_size: int
    overlap: int
    split_mode: str            # semantic | semantic_fallback | table_aware | clause | fixed
    separators: list[str]
    table_mode: str            # keep_whole | row_split | none


KB_AGENT_PROFILES: dict[str, dict] = {
    "macro_industry": {
        "enabled": True,
        "query_tpl": "{ticker} 宏观 政策 行业 政策影响",
    },
    "fundamentals": {
        "enabled": True,
        "query_tpl": "{ticker} 财报 业绩 资产负债 招股说明书",
    },
    "valuation": {
        "enabled": True,
        "query_tpl": "{ticker} 估值 可比公司 PE PB DCF",
    },
    "technicals": {
        "enabled": False,
        "query_tpl": "{ticker} 技术分析 K线 形态 指标",
    },
    "capital_sentiment": {
        "enabled": False,
        "query_tpl": "{ticker} 资金流向 北向 龙虎榜",
    },
}


CHUNK_STRATEGIES: dict[str, ChunkStrategy] = {
    "research": ChunkStrategy(
        name="research", chunk_size=800, overlap=100,
        split_mode="semantic",
        separators=["\n\n", "\n", "。", "；"],
        table_mode="keep_whole",
    ),
    "prospectus": ChunkStrategy(
        name="prospectus", chunk_size=800, overlap=100,
        split_mode="semantic_fallback",
        separators=["\n\n", "\n", "。", "；", "，"],
        table_mode="keep_whole",
    ),
    "annual_report": ChunkStrategy(
        name="annual_report", chunk_size=600, overlap=80,
        split_mode="table_aware",
        separators=["\n\n", "\n", "。"],
        table_mode="row_split",
    ),
    "quarterly_report": ChunkStrategy(
        name="quarterly_report", chunk_size=600, overlap=80,
        split_mode="table_aware",
        separators=["\n\n", "\n", "。"],
        table_mode="row_split",
    ),
    "regulatory_clause": ChunkStrategy(
        name="regulatory_clause", chunk_size=2000, overlap=0,
        split_mode="clause",
        separators=[r"第[一二三四五六七八九十百千\d]+条"],
        table_mode="keep_whole",
    ),
    "central_bank_report": ChunkStrategy(
        name="central_bank_report", chunk_size=700, overlap=100,
        split_mode="semantic",
        separators=["\n\n", "\n", "。", "；"],
        table_mode="keep_whole",
    ),
    "general": ChunkStrategy(
        name="general", chunk_size=500, overlap=80,
        split_mode="fixed",
        separators=["\n\n", "\n", "。", "；", "，", " "],
        table_mode="keep_whole",
    ),
}


VINTAGE_RULES: dict[str, int] = {
    "research": 6,
    "disclosure": 18,
    "general": 24,
    "regulatory": 36,
}


FIELD_ALIASES: dict[str, list[str]] = {
    "revenue": ["营业收入", "营业总收入"],
    "net_profit": ["归属于上市公司股东的净利润", "净利润"],
    "net_profit_excl_nonrecurring": ["扣除非经常性损益的净利润", "扣非净利润"],
    "eps": ["基本每股收益", "稀释每股收益"],
    "bvps": ["归属于上市公司股东的每股净资产", "每股净资产"],
    "roe": ["加权平均净资产收益率", "净资产收益率"],
    "total_assets": ["总资产", "资产总计"],
    "net_assets": ["归属于上市公司股东的净资产", "股东权益", "所有者权益"],
    "operating_cash_flow": ["经营活动产生的现金流量净额", "经营活动现金流量净额"],
}


_PROSPECTUS_SUBTYPES = {"招股说明书", "募集说明书"}
_ANNUAL_SUBTYPES = {"annual_report", "年报"}
_QUARTERLY_SUBTYPES = {"quarterly_report", "季报"}
_CENTRAL_BANK_SUBTYPES = {"央行货币政策报告", "central_bank_report"}


def select_strategy(category: str, sub_type: str) -> ChunkStrategy:
    """Pick chunk strategy by (category, sub_type)."""
    if category == "research":
        return CHUNK_STRATEGIES["research"]
    if category == "disclosure":
        if sub_type in _PROSPECTUS_SUBTYPES:
            return CHUNK_STRATEGIES["prospectus"]
        if sub_type in _ANNUAL_SUBTYPES:
            return CHUNK_STRATEGIES["annual_report"]
        if sub_type in _QUARTERLY_SUBTYPES:
            return CHUNK_STRATEGIES["quarterly_report"]
        return CHUNK_STRATEGIES["prospectus"]
    if category == "regulatory":
        if sub_type in _CENTRAL_BANK_SUBTYPES:
            return CHUNK_STRATEGIES["central_bank_report"]
        return CHUNK_STRATEGIES["regulatory_clause"]
    return CHUNK_STRATEGIES["general"]