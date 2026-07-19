"""Tests for BaoStock circuit breaker.

The breaker opens on login failure with cooldown scaled by error type:
- error_msg contains "黑名单" -> 30 min cooldown
- other errors -> 1 min cooldown
While open, ensure_login raises BaoStockUnavailable without calling bs.login.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from valor.adapters.data import baostock_client
from valor.adapters.data.baostock_client import (
    BaoStockUnavailable,
    _BLACKLIST_COOLDOWN_SEC,
    _OTHER_COOLDOWN_SEC,
    ensure_login,
    reset_circuit_breaker,
)


@pytest.fixture(autouse=True)
def _reset_circuit():
    reset_circuit_breaker()
    yield
    reset_circuit_breaker()


def _login_result(error_code: str, error_msg: str) -> SimpleNamespace:
    return SimpleNamespace(error_code=error_code, error_msg=error_msg)


def test_blacklist_error_opens_circuit_for_30_minutes():
    """bs.login() returning blacklist error opens circuit for 30 min."""
    with patch(
        "valor.adapters.data.baostock_client.bs.login",
        return_value=_login_result("1", "黑名单用户，请与管理员联系"),
    ):
        with pytest.raises(RuntimeError, match="黑名单"):
            ensure_login()

    # Subsequent call must raise BaoStockUnavailable WITHOUT calling bs.login
    with patch(
        "valor.adapters.data.baostock_client.bs.login",
        side_effect=AssertionError("bs.login should not be called when circuit open"),
    ):
        with pytest.raises(BaoStockUnavailable):
            ensure_login()


def test_other_login_error_opens_circuit_for_1_minute():
    """Non-blacklist login error opens circuit for 1 min only."""
    with patch(
        "valor.adapters.data.baostock_client.bs.login",
        return_value=_login_result("1", "network timeout"),
    ):
        with pytest.raises(RuntimeError, match="network timeout"):
            ensure_login()

    # Circuit should be open (1 min cooldown)
    with patch(
        "valor.adapters.data.baostock_client.bs.login",
        side_effect=AssertionError("bs.login should not be called when circuit open"),
    ):
        with pytest.raises(BaoStockUnavailable):
            ensure_login()


def test_circuit_closes_after_cooldown():
    """After cooldown elapses, ensure_login calls bs.login again."""
    with patch(
        "valor.adapters.data.baostock_client.bs.login",
        return_value=_login_result("1", "some error"),
    ):
        with pytest.raises(RuntimeError):
            ensure_login()

    # Fast-forward the reopen timestamp
    import valor.adapters.data.baostock_client as mod
    mod._CIRCUIT_REOPEN_AT = time.monotonic() - 1  # expired

    with patch(
        "valor.adapters.data.baostock_client.bs.login",
        return_value=_login_result("0", ""),
    ):
        ensure_login()  # should not raise


def test_successful_login_does_not_open_circuit():
    """A successful login leaves the circuit closed."""
    with patch(
        "valor.adapters.data.baostock_client.bs.login",
        return_value=_login_result("0", ""),
    ):
        ensure_login()

    assert baostock_client._CIRCUIT_REOPEN_AT is None


def test_cooldown_constants():
    """Sanity-check the cooldown constants."""
    assert _BLACKLIST_COOLDOWN_SEC == 30 * 60
    assert _OTHER_COOLDOWN_SEC == 60