"""Tests for ProxyManager retry logging.

Verifies that when proxy_manager is constructed with a logger, retry attempts
emit warning log records so users can diagnose transient failures.
"""

from __future__ import annotations

import logging
from io import StringIO

from valor.network.proxy_manager import ProxyManager


def test_proxy_manager_logs_retry_warnings() -> None:
    """Failed attempts emit a warning log record per attempt."""
    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.WARNING)
    logger = logging.getLogger("test_proxy_manager")
    logger.setLevel(logging.WARNING)
    logger.addHandler(handler)

    manager = ProxyManager(
        proxies=["direct"],
        max_attempts=3,
        base_delay=0,  # no real sleeps in tests
        max_delay=0,
        jitter=0,
        logger=logger,
    )

    def always_fail() -> None:
        raise ConnectionError("boom")

    try:
        manager.run(always_fail, "test_label")
    except ConnectionError:
        pass

    log_output = log_stream.getvalue()
    # Each failed attempt should produce a warning
    assert "attempt 1/3" in log_output
    assert "attempt 2/3" in log_output
    assert "attempt 3/3" in log_output
    # Final failure should produce an error
    assert "failed after 3 attempts" in log_output


def test_proxy_manager_no_logger_is_silent() -> None:
    """Without a logger, retries proceed silently (backward compat)."""
    manager = ProxyManager(
        proxies=["direct"],
        max_attempts=2,
        base_delay=0,
        max_delay=0,
        jitter=0,
        logger=None,
    )

    def always_fail() -> None:
        raise ConnectionError("boom")

    try:
        manager.run(always_fail, "test_label")
    except ConnectionError:
        pass
    # No assertion needed - just verify no exception from logging


def test_proxy_manager_from_env_accepts_logger() -> None:
    """ProxyManager.from_env(logger=...) wires the logger through."""
    logger = logging.getLogger("test_from_env")
    manager = ProxyManager.from_env(logger=logger)
    assert manager.logger is logger


def test_akshare_cache_proxy_manager_has_logger() -> None:
    """The module-level proxy_manager in akshare_cache must have a logger attached.

    Without a logger, retry attempts are silently swallowed and users cannot
    diagnose transient endpoint failures (e.g. EastMoney RemoteDisconnected).
    """
    from valor.adapters.data import akshare_cache

    assert akshare_cache.proxy_manager.logger is not None
