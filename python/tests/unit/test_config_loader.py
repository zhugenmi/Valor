"""Tests for the config_loader module."""

from valor.utils.config_loader import (
    get_cache_refresh_flag,
    get_news_limits,
    load_config,
)


def test_load_config_no_file():
    """load_config should return empty dict when no config.json exists."""
    config = load_config()
    assert isinstance(config, dict)
    assert config == {}


def test_get_cache_refresh_flag_default():
    """get_cache_refresh_flag should return default values for known agents."""
    # market_data_agent defaults to False for price_history
    flag = get_cache_refresh_flag("market_data_agent", "price_history")
    assert flag is False

    # capital_sentiment_agent defaults to True for news
    flag = get_cache_refresh_flag("capital_sentiment_agent", "news")
    assert flag is True


def test_get_news_limits_default():
    """get_news_limits should return default limits."""
    limits = get_news_limits()
    assert isinstance(limits, dict)
    assert limits["news_max_news"] == 100
    assert limits["tavily_max_news"] == 20
