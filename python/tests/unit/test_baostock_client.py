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
    baostock_client._LOGGED_IN = False
    yield
    reset_circuit_breaker()
    baostock_client._LOGGED_IN = False


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


# ---------------------------------------------------------------------------
# Index code detection: format_symbol / _is_index_symbol
# ---------------------------------------------------------------------------


def test_format_symbol_maps_sh_indexes_to_sh_prefix():
    """SH-listed indexes (000300 etc.) must map to sh. prefix, not sz."""
    from valor.adapters.data.baostock_client import format_symbol

    assert format_symbol("000300") == "sh.000300"  # 沪深300
    assert format_symbol("000016") == "sh.000016"  # 上证50
    assert format_symbol("000905") == "sh.000905"  # 中证500
    assert format_symbol("000852") == "sh.000852"  # 中证1000
    assert format_symbol("000010") == "sh.000010"  # 上证180


def test_format_symbol_keeps_sz_indexes_and_stocks_unchanged():
    """SZ indexes (399xxx) and stocks keep their existing mapping."""
    from valor.adapters.data.baostock_client import format_symbol

    assert format_symbol("399001") == "sz.399001"  # 深证成指
    assert format_symbol("399006") == "sz.399006"  # 创业板指
    assert format_symbol("600519") == "sh.600519"  # 茅台 (stock, unchanged)
    assert format_symbol("000858") == "sz.000858"  # 五粮液 (stock, unchanged)
    # 000001 is ambiguous (上证指数 vs 平安银行); default to stock (sz.)
    assert format_symbol("000001") == "sz.000001"


def test_format_symbol_passes_through_prefixed_codes():
    """Already-prefixed codes are returned lowercased unchanged."""
    from valor.adapters.data.baostock_client import format_symbol

    assert format_symbol("sh.000300") == "sh.000300"
    assert format_symbol("SZ.399001") == "sz.399001"


def test_is_index_symbol_detects_indexes():
    from valor.adapters.data.baostock_client import _is_index_symbol

    assert _is_index_symbol("000300") is True
    assert _is_index_symbol("000905") is True
    assert _is_index_symbol("399001") is True
    assert _is_index_symbol("399006") is True


def test_is_index_symbol_rejects_stocks():
    from valor.adapters.data.baostock_client import _is_index_symbol

    assert _is_index_symbol("600519") is False
    assert _is_index_symbol("000858") is False
    # 000001 is ambiguous - treated as stock unless caller prefixes sh.
    assert _is_index_symbol("000001") is False
    assert _is_index_symbol("sh.000001") is True
