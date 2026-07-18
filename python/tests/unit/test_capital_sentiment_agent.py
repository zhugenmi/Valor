"""Unit tests for capital_sentiment_agent.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

import json

from valor.agents.capital_sentiment import capital_sentiment_agent


def _make_state(ticker: str = "600519") -> dict:
    return {
        "messages": [],
        "data": {
            "ticker": ticker,
            "end_date": "2026-07-18",
            "portfolio": {"cash": 100000.0, "stock": 0},
        },
        "metadata": {"show_reasoning": False, "model": "openai"},
    }


def test_capital_sentiment_agent_returns_correct_message_name(monkeypatch):
    monkeypatch.setattr(
        "valor.agents.capital_sentiment.get_stock_news",
        lambda *a, **kw: [{"title": "t", "content": "c", "publish_time": "2026-07-15 10:00:00"}],
    )
    monkeypatch.setattr(
        "valor.agents.capital_sentiment.get_chat_completion",
        lambda messages: json.dumps({
            "sentiment": "bullish",
            "capital_flow": "inflow",
            "institutional_activity": "active",
            "turnover_analysis": "换手率上升",
            "risk_flags": [],
            "reasoning": "北向资金持续流入",
        }),
    )

    result = capital_sentiment_agent(_make_state())

    assert len(result["messages"]) == 1
    assert result["messages"][0].name == "capital_sentiment_agent"


def test_capital_sentiment_agent_output_schema(monkeypatch):
    monkeypatch.setattr(
        "valor.agents.capital_sentiment.get_stock_news",
        lambda *a, **kw: [{"title": "t", "content": "c", "publish_time": "2026-07-15 10:00:00"}],
    )
    monkeypatch.setattr(
        "valor.agents.capital_sentiment.get_chat_completion",
        lambda messages: json.dumps({
            "sentiment": "neutral",
            "capital_flow": "neutral",
            "institutional_activity": "quiet",
            "turnover_analysis": "成交清淡",
            "risk_flags": ["大股东减持"],
            "reasoning": "test",
        }),
    )

    result = capital_sentiment_agent(_make_state())
    content = json.loads(result["messages"][0].content)

    required = {
        "sentiment", "capital_flow", "institutional_activity",
        "turnover_analysis", "risk_flags", "reasoning",
    }
    assert required.issubset(content.keys())
    assert content["sentiment"] in {"bullish", "neutral", "bearish"}
    assert content["capital_flow"] in {"inflow", "neutral", "outflow"}
    assert isinstance(content["risk_flags"], list)


def test_capital_sentiment_agent_fetches_two_news_streams(monkeypatch):
    """Agent must call get_stock_news with two different agent_name parameters."""
    agent_names: list[str] = []

    def fake_get_stock_news(symbol, *a, **kw):
        agent_names.append(kw.get("agent_name", ""))
        return [{"title": "t", "content": "c", "publish_time": "2026-07-15 10:00:00"}]

    monkeypatch.setattr("valor.agents.capital_sentiment.get_stock_news", fake_get_stock_news)
    monkeypatch.setattr(
        "valor.agents.capital_sentiment.get_chat_completion",
        lambda messages: '{"sentiment":"neutral","capital_flow":"neutral","institutional_activity":"neutral","turnover_analysis":"n","risk_flags":[],"reasoning":"n"}',
    )

    capital_sentiment_agent(_make_state())

    assert "capital_sentiment_agent" in agent_names
    assert "capital_flow_agent" in agent_names


def test_capital_sentiment_agent_writes_data_field(monkeypatch):
    monkeypatch.setattr(
        "valor.agents.capital_sentiment.get_stock_news",
        lambda *a, **kw: [{"title": "t", "content": "c", "publish_time": "2026-07-15 10:00:00"}],
    )
    monkeypatch.setattr(
        "valor.agents.capital_sentiment.get_chat_completion",
        lambda messages: '{"sentiment":"neutral","capital_flow":"neutral","institutional_activity":"neutral","turnover_analysis":"n","risk_flags":[],"reasoning":"n"}',
    )

    result = capital_sentiment_agent(_make_state())

    assert "capital_sentiment_analysis" in result["data"]
