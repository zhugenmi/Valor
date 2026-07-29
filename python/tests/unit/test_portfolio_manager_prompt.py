"""Unit tests for portfolio_manager prompt construction - no hardcoded dimension keys.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from valor.agents import portfolio_manager as pm


def test_prompt_renders_dynamic_dimensions():
    """prompt should dynamically iterate reasoning, not hardcode profitability_signal etc."""
    # Simulate financial cluster output (no profitability_signal key, uses profitability)
    fundamental_signal = {
        "signal": "bullish",
        "confidence": 0.6,
        "reasoning": {
            "profitability": {"signal": "bullish", "details": "ROE 12%"},
            "financial_health": {"signal": "bullish", "details": "NPL 1.2%"},
        },
        "industry_profile": {"cluster": "financial", "cluster_label": "金融"},
    }
    text = pm._build_fundamental_block(fundamental_signal)
    assert "ROE 12%" in text
    assert "NPL 1.2%" in text
    # Should not show "无数据" due to key mismatch
    assert "盈利能力: 无数据" not in text


def test_prompt_handles_conglomerate_5_dimensions():
    """conglomerate 5 dimensions all render correctly."""
    fundamental_signal = {
        "signal": "neutral",
        "confidence": 0.4,
        "reasoning": {
            "profitability": {"details": "ROE 18%"},
            "growth": {"details": "营收增长 15%"},
            "financial_health": {"details": "流动比率 2.0"},
            "valuation": {"details": "PE 20"},
            "shareholder_return": {"details": "股息率 5%"},
        },
    }
    text = pm._build_fundamental_block(fundamental_signal)
    for key in ["ROE 18%", "营收增长 15%", "流动比率 2.0", "PE 20", "股息率 5%"]:
        assert key in text


def test_prompt_handles_none_signal():
    """None fundamental_signal returns a placeholder."""
    text = pm._build_fundamental_block(None)
    assert "无数据" in text


def test_prompt_handles_empty_reasoning():
    """Empty reasoning dict returns a placeholder."""
    fundamental_signal = {"signal": "neutral", "reasoning": {}}
    text = pm._build_fundamental_block(fundamental_signal)
    assert "无数据" in text


def test_prompt_handles_unknown_dimension_name():
    """Unknown dimension names use the raw key as label."""
    fundamental_signal = {
        "signal": "bullish",
        "reasoning": {
            "custom_metric": {"details": "custom detail 123"},
        },
    }
    text = pm._build_fundamental_block(fundamental_signal)
    assert "custom_metric" in text
    assert "custom detail 123" in text