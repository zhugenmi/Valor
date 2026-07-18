"""Capital flow + Sentiment analyst agent.

Renamed and expanded from the former sentiment_agent. Covers the 6-dimension
framework's "资金面与情绪" dimension: market sentiment, capital flow
(northbound/institutional/dragon-tiger), and a dilution/lockup risk scan.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

import json
import re
from datetime import datetime, timedelta

from langchain_core.messages import HumanMessage

from valor.agents.state import AgentState, show_agent_reasoning, show_workflow_status
from valor.tools.news_crawler import get_stock_news
from valor.tools.openrouter_config import get_chat_completion
from valor.utils.api_utils import agent_endpoint, log_llm_interaction
from valor.utils.config_loader import get_news_limits
from valor.utils.logging_config import setup_logger
from valor.utils.prompt_loader import format_prompt, load_prompt

logger = setup_logger("capital_sentiment_agent")


def _filter_recent_news(news_list: list, days: int = 7) -> list:
    cutoff = datetime.now() - timedelta(days=days)
    recent: list = []
    for news in news_list:
        publish_time = news.get("publish_time")
        if not publish_time:
            recent.append(news)
            continue
        try:
            news_date = datetime.strptime(publish_time, "%Y-%m-%d %H:%M:%S")
            if news_date > cutoff:
                recent.append(news)
        except ValueError:
            recent.append(news)
    return recent


def _format_news_block(news_list: list, limit: int = 25) -> str:
    blocks: list[str] = []
    for news in news_list[:limit]:
        blocks.append(
            f"标题：{news.get('title', '未知')}\n"
            f"来源：{news.get('source', '未知')}\n"
            f"时间：{news.get('publish_time', news.get('search_time', '未知'))}\n"
            f"内容：{news.get('content', '')}"
        )
    return "\n\n".join(blocks)


def _parse_llm_json(raw: str) -> dict | None:
    if not raw:
        return None
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        match = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                return None
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if 0 <= start < end:
            try:
                return json.loads(raw[start:end])
            except json.JSONDecodeError:
                return None
    return None


def _default_payload(reasoning: str) -> dict:
    return {
        "sentiment": "neutral",
        "capital_flow": "neutral",
        "institutional_activity": "quiet",
        "turnover_analysis": "无可用数据",
        "risk_flags": [],
        "reasoning": reasoning,
    }


@agent_endpoint("capital_sentiment", "资金面与情绪分析师，覆盖市场情绪/资金流向/减持解禁风险扫描")
def capital_sentiment_agent(state: AgentState):
    """Expanded capital flow + sentiment analysis agent."""
    show_workflow_status("Capital Sentiment Analyst")
    show_reasoning = state["metadata"]["show_reasoning"]
    data = state["data"]
    symbol = data["ticker"]
    end_date = data.get("end_date")
    logger.info("💰 正在进行资金面与情绪分析: %s", symbol)

    limits = get_news_limits()
    try:
        news_limit = max(1, int(limits.get("news_max_news", 10)))
    except (TypeError, ValueError):
        news_limit = 10

    # Fetch both sentiment news and capital-flow news
    sentiment_news = get_stock_news(
        symbol, max_news=news_limit, date=end_date,
        agent_name="capital_sentiment_agent", trace_state=state,
    )
    capital_news = get_stock_news(
        symbol, max_news=news_limit, date=end_date,
        agent_name="capital_flow_agent", trace_state=state,
    )

    recent_sentiment = _filter_recent_news(sentiment_news)
    recent_capital = _filter_recent_news(capital_news)
    logger.info(
        "🗞️ 情绪新闻 %d 条 / 资金面新闻 %d 条",
        len(recent_sentiment), len(recent_capital),
    )

    if not recent_sentiment and not recent_capital:
        logger.warning("⚠️ 未获取到任何新闻，使用默认中性结果")
        message_content = _default_payload("未获取到最近新闻，无法进行资金面与情绪分析")
    else:
        sentiment_block = _format_news_block(recent_sentiment)
        capital_block = _format_news_block(recent_capital)

        system_message = {
            "role": "system",
            "content": load_prompt("prompts/capital_sentiment/system.md"),
        }
        user_message = {
            "role": "user",
            "content": format_prompt(
                "prompts/capital_sentiment/user.md",
                ticker=symbol,
                sentiment_news_content=sentiment_block,
                capital_news_content=capital_block,
            ),
        }

        try:
            logger.info("🤖 调用 LLM 进行资金面与情绪分析...")
            raw_response = log_llm_interaction(state)(get_chat_completion)(
                [system_message, user_message]
            )
            parsed = _parse_llm_json(raw_response)
            if parsed is None:
                logger.error("❌ 无法解析 LLM 返回的 JSON")
                message_content = _default_payload("LLM 返回的 JSON 无法解析")
            else:
                message_content = {
                    "sentiment": parsed.get("sentiment", "neutral"),
                    "capital_flow": parsed.get("capital_flow", "neutral"),
                    "institutional_activity": parsed.get("institutional_activity", "quiet"),
                    "turnover_analysis": parsed.get("turnover_analysis", ""),
                    "risk_flags": parsed.get("risk_flags", []) or [],
                    "reasoning": parsed.get("reasoning", ""),
                }
                logger.info(
                    "✅ 资金面与情绪分析完成: sentiment=%s flow=%s",
                    message_content["sentiment"],
                    message_content["capital_flow"],
                )
        except Exception as exc:
            logger.error("❌ 资金面与情绪分析出错: %s", exc)
            message_content = _default_payload(f"分析过程中出错: {exc}")

    if show_reasoning:
        show_agent_reasoning(message_content, "Capital Sentiment Analyst")
        state["metadata"]["agent_reasoning"] = message_content

    message = HumanMessage(
        content=json.dumps(message_content, ensure_ascii=False),
        name="capital_sentiment_agent",
    )

    show_workflow_status("Capital Sentiment Analyst", "completed")
    return {
        "messages": state["messages"] + [message],
        "data": {**data, "capital_sentiment_analysis": message_content},
        "metadata": state["metadata"],
    }
