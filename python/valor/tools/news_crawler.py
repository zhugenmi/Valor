"""News crawler shim - retrieves stock news from AkShare.

Phase 1B simplified version. Uses AkShare's stock news endpoint directly
instead of Tavily. In future phases this will be wired to a proper news API.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from loguru import logger

from valor.adapters.data.sqlite_cache import AkshareSQLiteCache
from valor.tools.news_query_builder import build_news_query
from valor.utils.config_loader import get_cache_refresh_flag, get_news_limits

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
NEWS_CACHE_DB_PATH = BASE_DIR / "data" / "market_data_cache.db"
NEWS_CACHE_TABLE = "stock_news_daily_cache"
MAX_NEWS_CAP = 50


def _normalize_date_str(value: str | None) -> str:
    text = (value or "").strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return datetime.now().strftime("%Y-%m-%d")


def _build_date_window(end_date: str, days_back: int = 7) -> tuple[str, str]:
    try:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    except Exception:
        end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=max(1, days_back))
    return start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")


def _fetch_akshare_news(symbol: str) -> list[dict]:
    """Fetch news from AkShare's stock news endpoint."""
    try:
        import akshare as ak

        df = ak.stock_news_em(symbol=symbol)
        if df is None or df.empty:
            return []
        news_list = []
        for _, row in df.iterrows():
            news_list.append({
                "title": row.get("新闻标题", row.get("title", row.get("标题", ""))),
                "content": row.get("新闻内容", row.get("content", row.get("内容", ""))),
                "publish_time": str(row.get("发布时间", row.get("publish_time", ""))),
                "source": row.get("文章来源", row.get("source", "东方财富")),
            })
        return news_list
    except Exception as e:
        logger.warning("AkShare news fetch failed for {s}: {err}", s=symbol, err=e)
        return []


def _sort_news_items(items: list) -> list:
    def _key(x):
        return x.get("publish_time") or ""
    return sorted(items, key=_key, reverse=True)


def get_stock_news(
    symbol: str,
    max_news: int = 10,
    date: str | None = None,
    *,
    agent_name: str | None = None,
    trace_state: dict | None = None,
) -> list:
    """Get stock news.

    Phase 1B: Uses AkShare's news endpoint as the primary source.
    Falls back to empty list if AkShare is unavailable.

    Args:
        symbol: Stock ticker
        max_news: Maximum number of news items
        date: Cutoff date (YYYY-MM-DD)
        agent_name: Agent name (for cache refresh flags)
        trace_state: Tracking state

    Returns:
        List of news dicts with title, content, publish_time, source
    """
    limits = get_news_limits()
    try:
        config_news_max = max(1, int(limits.get("news_max_news", 100)))
    except (TypeError, ValueError):
        config_news_max = 100
    max_news = min(max_news, config_news_max, MAX_NEWS_CAP)

    cache_date = _normalize_date_str(date)

    # Check cache refresh flag
    refresh_news = False
    if agent_name:
        refresh_news = get_cache_refresh_flag(agent_name, "news")

    # Try cache
    import os
    cache_dir = os.path.dirname(str(NEWS_CACHE_DB_PATH))
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir, exist_ok=True)
    cache = AkshareSQLiteCache(database_path=NEWS_CACHE_DB_PATH)

    cached_news = []
    if not refresh_news:
        try:
            cached_records = cache.fetch_records(
                NEWS_CACHE_TABLE,
                filters={"symbol": symbol, "cache_date": cache_date},
                limit=1,
            )
            if cached_records:
                record = dict(cached_records[0])
                record.pop("缓存时间", None)
                news_json = record.get("news_json")
                if news_json:
                    cached_news = json.loads(news_json)
        except Exception:
            pass

    if len(cached_news) >= max_news:
        logger.info("News cache hit: {s} {d} ({n} items)", s=symbol, d=cache_date, n=len(cached_news))
        return cached_news[:max_news]

    # Fetch fresh news from AkShare
    fresh_news = _fetch_akshare_news(symbol) or []

    # Merge with cache (dedup by title)
    combined = cached_news[:]
    existing_titles = {item.get("title", "") for item in combined}

    for item in fresh_news:
        title = item.get("title", "")
        if title and title not in existing_titles:
            combined.append(item)
            existing_titles.add(title)

    combined = _sort_news_items(combined)

    # Write back to cache
    if len(combined) > len(cached_news):
        try:
            row = {
                "symbol": symbol,
                "cache_date": cache_date,
                "news_json": json.dumps(combined, ensure_ascii=False),
                "news_count": len(combined),
                "method": "akshare",
                "search_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            cache.upsert_records(NEWS_CACHE_TABLE, [row], key_columns=["symbol", "cache_date"])
        except Exception:
            pass

    return combined[:max_news]


# Legacy entry point
def build_search_query(symbol: str, date: str | None = None) -> str:
    """Legacy entry point."""
    return build_news_query(symbol, date=date)
