"""Market snapshot - generates AI-powered stock market snapshots.

Simplified Phase 1B version using valor's LLM adapter.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from loguru import logger

from valor.adapters.data.sqlite_cache import AkshareSQLiteCache
from valor.tools.news_crawler import get_stock_news
from valor.tools.openrouter_config import get_chat_completion
from valor.utils.api_utils import log_llm_interaction
from valor.utils.config_loader import get_cache_refresh_flag, get_news_limits
from valor.utils.prompt_loader import format_prompt, load_prompt

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
CACHE_PATH = BASE_DIR / "data" / "market_data_cache.db"
SNAPSHOT_TABLE = "market_snapshot_cache"
SNAPSHOT_TTL_SECONDS = 24 * 3600

logger_info = logger


def _parse_numeric(value: Any, default_multiplier: float | None = None) -> float:
    """Parse numeric fields supporting Chinese units (亿/万)."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        number = float(value)
        if default_multiplier and number < default_multiplier:
            number *= default_multiplier
        return number
    text = str(value).strip()
    if not text:
        return 0.0

    unit_tokens = [
        ("万亿", 1e12), ("亿股", 1e8), ("亿手", 1e8), ("亿", 1e8),
        ("万股", 1e4), ("万手", 1e4), ("万", 1e4),
    ]
    multiplier = 1.0
    for token, factor in unit_tokens:
        if token in text:
            text = text.replace(token, "")
            multiplier = factor
            break

    cleaned = text.replace(",", "").replace(" ", "")
    match = re.search(r"-?\d+(\.\d+)?", cleaned)
    if not match:
        return 0.0
    number = float(match.group())
    if not any(t[0] in str(value) for t in unit_tokens) and default_multiplier:
        number *= default_multiplier
    return number * multiplier


def _sanitize_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    market_cap = _parse_numeric(data.get("market_cap"), default_multiplier=1e8)
    volume = _parse_numeric(data.get("volume"), default_multiplier=1e8)
    average_volume = _parse_numeric(data.get("average_volume"), default_multiplier=1e8)
    high = _parse_numeric(data.get("fifty_two_week_high"))
    low = _parse_numeric(data.get("fifty_two_week_low"))

    try:
        confidence = float(data.get("confidence", 0) or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    return {
        "market_cap": market_cap,
        "volume": volume,
        "average_volume": average_volume,
        "fifty_two_week_high": high,
        "fifty_two_week_low": low,
        "confidence": confidence,
        "summary": str(data.get("summary", "")).strip(),
    }


def _build_prompt(symbol: str, news_items: list[dict]) -> list[dict[str, str]]:
    if not news_items:
        news_block = "暂无最新新闻，请给出一个基于常识的高层次总结。"
    else:
        lines = []
        for item in news_items[:10]:
            lines.append(
                f"标题：{item.get('title', '未知')}\n"
                f"来源：{item.get('source', '未知')}\n"
                f"时间：{item.get('publish_time', '')}\n"
                f"内容：{item.get('content', '')}"
            )
        news_block = "\n\n".join(lines)

    system_message = load_prompt("prompts/market_snapshot/system.md")
    user_message = format_prompt("prompts/market_snapshot/user.md", symbol=symbol, news_block=news_block)
    return [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message},
    ]


def _parse_snapshot_response(raw: str) -> dict[str, Any]:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        try:
            start = raw.index("{")
            end = raw.rindex("}") + 1
            return json.loads(raw[start:end])
        except Exception:
            return {}


def _generate_snapshot(
    symbol: str,
    trace_state: dict | None = None,
    as_of_date: str | None = None,
) -> dict[str, Any]:
    limits = get_news_limits()
    try:
        news_limit = max(1, int(limits.get("news_max_news", 10)))
    except (TypeError, ValueError):
        news_limit = 10

    news_items = get_stock_news(
        symbol, max_news=news_limit, date=as_of_date,
        agent_name="market_snapshot", trace_state=trace_state,
    )
    logger.info("Snapshot news pool for {s}: {n} items", s=symbol, n=len(news_items))

    messages = _build_prompt(symbol, news_items)
    logger.info("Calling LLM for {s} market snapshot...", s=symbol)

    try:
        if trace_state:
            llm_response = log_llm_interaction(trace_state)(get_chat_completion)(messages)
        else:
            llm_response = get_chat_completion(messages)
    except Exception as exc:
        logger.error("Market snapshot LLM call failed: {err}", err=exc)
        llm_response = None

    snapshot_raw = _parse_snapshot_response(llm_response or "{}")
    sanitized = _sanitize_snapshot(snapshot_raw)
    sanitized.setdefault("summary", "")
    sanitized["news_count"] = len(news_items)
    return sanitized


def get_market_snapshot(
    symbol: str,
    ttl_seconds: int = SNAPSHOT_TTL_SECONDS,
    *,
    trace_state: dict | None = None,
    agent_name: str | None = None,
    as_of_date: str | None = None,
) -> dict[str, Any]:
    """Get an AI-generated market snapshot for a ticker.

    Returns a dict with market_cap, volume, confidence, summary, etc.
    Falls back to empty values if LLM is unavailable.
    """
    refresh_snapshot = get_cache_refresh_flag(agent_name or "market_snapshot", "snapshot")
    cache_date = as_of_date or datetime.now().strftime("%Y-%m-%d")

    # Try cache first
    import os
    cache_dir = os.path.dirname(str(CACHE_PATH))
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir, exist_ok=True)
    cache = AkshareSQLiteCache(database_path=CACHE_PATH)

    if not refresh_snapshot:
        try:
            cached = cache.fetch_records(
                table=SNAPSHOT_TABLE,
                filters={"symbol": symbol, "cache_date": cache_date},
                ttl_seconds=ttl_seconds,
                order_by='"缓存时间" DESC',
                limit=1,
            )
            if cached:
                record = dict(cached[0])
                record.pop("缓存时间", None)
                logger.info("Market snapshot cache hit for {s} ({d})", s=symbol, d=cache_date)
                return record
        except Exception:
            pass

    snapshot = _generate_snapshot(symbol, trace_state=trace_state, as_of_date=cache_date)
    record = {"symbol": symbol, "cache_date": cache_date, **snapshot}

    try:
        cache.upsert_records(SNAPSHOT_TABLE, [record], key_columns=["symbol", "cache_date"])
    except Exception:
        pass

    logger.info("Market snapshot refreshed for {s}", s=symbol)
    return record
