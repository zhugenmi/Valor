"""Unit tests for risk_manager fallback when debate fails.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

import json

from langchain_core.messages import HumanMessage

from valor.agents.risk_manager import risk_management_agent


def _dim_msg(name: str, signal: str) -> HumanMessage:
    return HumanMessage(
        content=json.dumps({"signal": signal, "confidence": "60%", "reasoning": "test"}),
        name=name,
    )


def _debate_failed_msg() -> HumanMessage:
    """模拟 debate 全部失败（confidence=0.0）的消息。"""
    return HumanMessage(
        content=json.dumps({
            "signal": "neutral",
            "confidence": 0.0,
            "bull_confidence": 0.0,
            "bear_confidence": 0.0,
        }),
        name="bull_bear_debate_agent",
    )


def _make_prices(n: int = 150) -> list[dict]:
    """生成 n 天缓慢上涨的低波动价格数据，避免触发 market_risk_score 加分。"""
    return [{"close": 10.0 + i * 0.01} for i in range(n)]


def _make_state(dim_signals: dict[str, str]) -> dict:
    """构造 AgentState，dim_signals 指定每个维度代理的 signal。"""
    messages = [
        _dim_msg("technical_analyst_agent", dim_signals.get("technical", "neutral")),
        _dim_msg("fundamentals_agent", dim_signals.get("fundamentals", "neutral")),
        _dim_msg("valuation_agent", dim_signals.get("valuation", "neutral")),
        _dim_msg("capital_sentiment_agent", dim_signals.get("sentiment", "neutral")),
        _dim_msg("macro_industry_agent", dim_signals.get("macro", "neutral")),
        _debate_failed_msg(),
    ]
    return {
        "messages": messages,
        "data": {
            "ticker": "601728",
            "portfolio": {"cash": 100000.0, "stock": 0},
            "prices": _make_prices(),
        },
        "metadata": {"show_reasoning": False, "model": "openai"},
    }


def test_fallback_triggers_buy_when_bullish_majority():
    """debate 失败 + 3 bullish 2 bearish -> trading_action=buy。"""
    state = _make_state({
        "technical": "bullish",
        "fundamentals": "bullish",
        "valuation": "bullish",
        "sentiment": "bearish",
        "macro": "bearish",
    })
    result = risk_management_agent(state)
    risk_analysis = result["data"]["risk_analysis"]
    assert risk_analysis["trading_action"] == "buy"
    assert risk_analysis["debate_analysis"]["debate_signal"] == "bullish"
    assert risk_analysis["debate_analysis"]["debate_confidence"] == 0.6


def test_fallback_triggers_sell_when_bearish_majority():
    """debate 失败 + 2 bullish 3 bearish -> trading_action=sell。"""
    state = _make_state({
        "technical": "bearish",
        "fundamentals": "bearish",
        "valuation": "bearish",
        "sentiment": "bullish",
        "macro": "bullish",
    })
    result = risk_management_agent(state)
    risk_analysis = result["data"]["risk_analysis"]
    assert risk_analysis["trading_action"] == "sell"
    assert risk_analysis["debate_analysis"]["debate_signal"] == "bearish"
    assert risk_analysis["debate_analysis"]["debate_confidence"] == 0.6


def test_fallback_neutral_when_tied():
    """debate 失败 + 2 bullish 2 bearish 1 neutral -> 平票 -> trading_action=hold。"""
    state = _make_state({
        "technical": "bullish",
        "fundamentals": "bullish",
        "valuation": "bearish",
        "sentiment": "bearish",
        "macro": "neutral",
    })
    result = risk_management_agent(state)
    risk_analysis = result["data"]["risk_analysis"]
    assert risk_analysis["debate_analysis"]["debate_signal"] == "neutral"
    assert risk_analysis["debate_analysis"]["debate_confidence"] == 0.3
    # debate_confidence=0.3 < 0.5, 不触发 buy/sell, 默认 hold
    assert risk_analysis["trading_action"] == "hold"


def test_no_fallback_when_debate_succeeded():
    """debate 成功（confidence>0）时不触发 fallback，按原逻辑处理。"""
    messages = [
        _dim_msg("technical_analyst_agent", "bullish"),
        _dim_msg("fundamentals_agent", "bullish"),
        _dim_msg("valuation_agent", "bullish"),
        _dim_msg("capital_sentiment_agent", "bearish"),
        _dim_msg("macro_industry_agent", "bearish"),
        HumanMessage(
            content=json.dumps({
                "signal": "bullish",
                "confidence": 0.7,
                "bull_confidence": 0.7,
                "bear_confidence": 0.3,
            }),
            name="bull_bear_debate_agent",
        ),
    ]
    state = {
        "messages": messages,
        "data": {
            "ticker": "601728",
            "portfolio": {"cash": 100000.0, "stock": 0},
            "prices": _make_prices(),
        },
        "metadata": {"show_reasoning": False, "model": "openai"},
    }
    result = risk_management_agent(state)
    risk_analysis = result["data"]["risk_analysis"]
    # debate 成功时 debate_confidence 保持 0.7（未被 fallback 覆盖）
    assert risk_analysis["debate_analysis"]["debate_confidence"] == 0.7
    assert risk_analysis["debate_analysis"]["debate_signal"] == "bullish"
    assert risk_analysis["trading_action"] == "buy"
