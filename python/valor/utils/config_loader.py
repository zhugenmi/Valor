"""Configuration loader - cache refresh flags and news limits.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

import json
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[2]
CONFIG_PATH = BASE_DIR / "config.json"

DEFAULT_CACHE_REFRESH: dict[str, dict[str, bool]] = {
    "market_data_agent": {
        "price_history": False,
        "financial_indicators": False,
        "financial_reports": False,
        "market_snapshot": False,
    },
    "market_snapshot": {"news": True, "snapshot": False},
    "capital_sentiment_agent": {"news": True},
    "capital_flow_agent": {"news": True},
    "macro_industry_agent": {"news": True},
}

DEFAULT_NEWS_LIMITS: dict[str, int] = {
    "news_max_news": 100,
    "tavily_max_news": 20,
}


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def get_cache_refresh_config() -> dict[str, dict[str, bool]]:
    config = load_config()
    user_cfg = config.get("cache_refresh", {})
    if not isinstance(user_cfg, dict):
        user_cfg = {}
    return _deep_merge(DEFAULT_CACHE_REFRESH, user_cfg)


def get_cache_refresh_flag(agent_name: str, cache_key: str) -> bool:
    merged = get_cache_refresh_config()
    agent_cfg = merged.get(agent_name, {})
    if isinstance(agent_cfg, dict):
        return bool(agent_cfg.get(cache_key, False))
    return bool(agent_cfg)


def get_news_limits() -> dict[str, int]:
    config = load_config()
    user_cfg = config.get("news_limits", {})
    if not isinstance(user_cfg, dict):
        user_cfg = {}
    return _deep_merge(DEFAULT_NEWS_LIMITS, user_cfg)
