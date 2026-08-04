"""Macro + Industry analyst agent.

Merges the former macro_analyst (stock-specific macro news) and macro_news_agent
(market-wide macro news) into a single agent that also covers industry analysis.
Aligned with the 6-dimension framework's "宏观与行业" dimension.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

import json
import re
from datetime import datetime, timedelta

from langchain_core.messages import HumanMessage

from valor.agents.state import AgentState, show_agent_reasoning, show_workflow_status
from valor.core.protocols import Citation
from valor.tools.news_crawler import get_stock_news
from valor.tools.openrouter_config import get_chat_completion
from valor.utils.api_utils import agent_endpoint, log_llm_interaction
from valor.utils.config_loader import get_news_limits
from valor.utils.logging_config import setup_logger
from valor.utils.prompt_loader import format_prompt, load_prompt

logger = setup_logger("macro_industry_agent")

MARKET_INDEX_SYMBOL = "沪深300指数"


def _filter_recent_news(news_list: list, days: int = 7) -> list:
    """Keep only news published within the last `days` days."""
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
    """Render news items into a single text block for the LLM prompt."""
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
    """Parse LLM response as JSON, tolerant of ```json code fences."""
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
        # Last resort: extract first {...} block
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
        "macro_environment": "neutral",
        "industry_outlook": "neutral",
        "policy_impact": "neutral",
        "key_factors": [],
        "risk_flags": [],
        "evidence": [],
        "reasoning": reasoning,
    }


def _build_kb_section(kb_ctx: dict) -> str:
    """Build KB context section for user message. Empty if skipped/no chunks."""
    if not kb_ctx or kb_ctx.get("skipped"):
        return ""
    chunks = kb_ctx.get("chunks") or []
    if not chunks:
        return ""
    lines = ["## 知识库参考（按相关性排序）"]
    for i, c in enumerate(chunks, 1):
        lines.append(
            f"[C{i}]《{c.get('doc_title', '')}》"
            f"(发布: {c.get('publish_date', '未知')}, 时效: {c.get('vintage', 'unknown')})"
        )
        lines.append(f"  正文：{c.get('text', '')}")
    return "\n".join(lines)


def _extract_citations(text: str, kb_ctx: dict) -> list[Citation]:
    """Extract [Cn] references from LLM output and map to chunks."""
    if not kb_ctx or kb_ctx.get("skipped"):
        return []
    chunks = kb_ctx.get("chunks") or []
    if not chunks:
        return []
    refs = set(re.findall(r"\[C(\d+)\]", text))
    citations = []
    for ref in sorted(refs, key=int):
        idx = int(ref) - 1
        if 0 <= idx < len(chunks):
            c = chunks[idx]
            citations.append(Citation(
                chunk_id=c.get("chunk_id", ""),
                doc_id=c.get("doc_id", ""),
                doc_title=c.get("doc_title", ""),
                publish_date=c.get("publish_date", ""),
                vintage=c.get("vintage", "unknown"),
                page_no=c.get("page_no"),
                cited_text=c.get("text", "")[:200],
            ))
    return citations


@agent_endpoint("macro_industry", "宏观与行业分析师，覆盖宏观经济/行业前景/政策影响/政策风险扫描")
def macro_industry_agent(state: AgentState):
    """Merged macro + industry analysis agent."""
    show_workflow_status("Macro Industry Analyst")
    show_reasoning = state["metadata"]["show_reasoning"]
    data = state["data"]
    symbol = data["ticker"]
    end_date = data.get("end_date")
    citations: list[Citation] = []
    logger.info("🧠 正在进行宏观与行业分析: %s", symbol)

    limits = get_news_limits()
    try:
        news_limit = max(1, int(limits.get("news_max_news", 10)))
    except (TypeError, ValueError):
        news_limit = 10

    # Fetch both stock-specific and market-wide macro news
    stock_news = get_stock_news(
        symbol, max_news=news_limit, date=end_date,
        agent_name="macro_industry_agent", trace_state=state,
    )
    market_news = get_stock_news(
        MARKET_INDEX_SYMBOL, max_news=news_limit, date=end_date,
        agent_name="macro_industry_agent", trace_state=state,
    )

    recent_stock = _filter_recent_news(stock_news)
    recent_market = _filter_recent_news(market_news)
    logger.info(
        "📰 个股宏观新闻 %d 条 / 大盘宏观新闻 %d 条",
        len(recent_stock), len(recent_market),
    )

    if not recent_stock and not recent_market:
        logger.warning("⚠️ 未获取到任何宏观新闻，使用默认中性结果")
        message_content = _default_payload("未获取到最近新闻，无法进行宏观与行业分析")
    else:
        stock_block = _format_news_block(recent_stock)
        market_block = _format_news_block(recent_market)

        kb_ctx = state["data"].get("kb_context", {}).get("macro_industry", {})
        kb_section = _build_kb_section(kb_ctx)

        system_message = {
            "role": "system",
            "content": load_prompt("prompts/macro_industry/system.md"),
        }
        user_content = format_prompt(
            "prompts/macro_industry/user.md",
            ticker=symbol,
            stock_news_content=stock_block,
            market_news_content=market_block,
        )
        if kb_section:
            user_content = user_content + "\n\n" + kb_section
        user_message = {
            "role": "user",
            "content": user_content,
        }

        try:
            logger.info("🤖 调用 LLM 进行宏观与行业分析...")
            raw_response = log_llm_interaction(state)(get_chat_completion)(
                [system_message, user_message]
            )
            parsed = _parse_llm_json(raw_response)
            if parsed is None:
                logger.error("❌ 无法解析 LLM 返回的 JSON")
                message_content = _default_payload("LLM 返回的 JSON 无法解析")
            else:
                # Ensure all required fields exist
                message_content = {
                    "macro_environment": parsed.get("macro_environment", "neutral"),
                    "industry_outlook": parsed.get("industry_outlook", "neutral"),
                    "policy_impact": parsed.get("policy_impact", "neutral"),
                    "key_factors": parsed.get("key_factors", []) or [],
                    "risk_flags": parsed.get("risk_flags", []) or [],
                    "evidence": parsed.get("evidence", []) or [],
                    "reasoning": parsed.get("reasoning", ""),
                }
                citations = _extract_citations(raw_response, kb_ctx)
                message_content["citations"] = [c.model_dump() for c in citations]
                logger.info(
                    "📊 宏观与行业分析完成: macro=%s industry=%s policy=%s",
                    message_content["macro_environment"],
                    message_content["industry_outlook"],
                    message_content["policy_impact"],
                )
        except Exception as exc:
            logger.error("❌ 宏观与行业分析出错: %s", exc)
            message_content = _default_payload(f"分析过程中出错: {exc}")

    if show_reasoning:
        show_agent_reasoning(message_content, "Macro Industry Analyst")
        state["metadata"]["agent_reasoning"] = message_content

    message = HumanMessage(
        content=json.dumps(message_content, ensure_ascii=False),
        name="macro_industry_agent",
    )

    show_workflow_status("Macro Industry Analyst", "completed")
    return {
        "messages": state["messages"] + [message],
        "data": {**data, "macro_industry_analysis": message_content},
        "metadata": {**state["metadata"], "macro_industry_citations": citations},
    }
