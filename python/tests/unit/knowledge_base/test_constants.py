"""Tests for knowledge_base.constants. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from valor.knowledge_base.constants import (
    CHUNK_STRATEGIES,
    FIELD_ALIASES,
    KB_AGENT_PROFILES,
    VINTAGE_RULES,
    ChunkStrategy,
    select_strategy,
)


def test_kb_agent_profiles_cover_5_analysis_agents():
    expected = {"macro_industry", "fundamentals", "valuation", "technicals", "capital_sentiment"}
    assert expected <= set(KB_AGENT_PROFILES.keys())
    for name, profile in KB_AGENT_PROFILES.items():
        assert "enabled" in profile
        assert "query_tpl" in profile
        assert "{ticker}" in profile["query_tpl"]


def test_chunk_strategies_has_7_strategies():
    expected = {
        "research", "prospectus", "annual_report", "quarterly_report",
        "regulatory_clause", "central_bank_report", "general",
    }
    assert set(CHUNK_STRATEGIES.keys()) == expected


def test_chunk_strategy_fields():
    s = CHUNK_STRATEGIES["research"]
    assert isinstance(s, ChunkStrategy)
    assert s.chunk_size == 800
    assert s.overlap == 100
    assert s.split_mode == "semantic"
    assert s.table_mode == "keep_whole"


def test_select_strategy_research():
    s = select_strategy("research", "公司研究")
    assert s.name == "research"


def test_select_strategy_disclosure_prospectus():
    s = select_strategy("disclosure", "招股说明书")
    assert s.name == "prospectus"


def test_select_strategy_disclosure_annual():
    s = select_strategy("disclosure", "annual_report")
    assert s.name == "annual_report"


def test_select_strategy_regulatory_clause():
    s = select_strategy("regulatory", "行业监管规定")
    assert s.name == "regulatory_clause"


def test_select_strategy_regulatory_central_bank():
    s = select_strategy("regulatory", "央行货币政策报告")
    assert s.name == "central_bank_report"


def test_select_strategy_general_fallback():
    s = select_strategy("general", "行政文书")
    assert s.name == "general"


def test_vintage_rules_has_4_categories():
    assert VINTAGE_RULES == {
        "research": 6,
        "disclosure": 18,
        "general": 24,
        "regulatory": 36,
    }


def test_field_aliases_cover_9_mvp_fields():
    expected = {
        "revenue", "net_profit", "net_profit_excl_nonrecurring", "eps",
        "bvps", "roe", "total_assets", "net_assets", "operating_cash_flow",
    }
    assert set(FIELD_ALIASES.keys()) == expected
    assert "营业收入" in FIELD_ALIASES["revenue"]
    assert "归属于上市公司股东的净利润" in FIELD_ALIASES["net_profit"]