import atexit
import threading
import time
from datetime import datetime
from typing import List

import baostock as bs
import pandas as pd

from valor.utils.logging_config import setup_logger

logger = setup_logger("baostock_client")
_LOGIN_LOCK = threading.Lock()
_LOGGED_IN = False

# Circuit breaker cooldowns (seconds)
_BLACKLIST_COOLDOWN_SEC = 30 * 60  # 30 min for blacklist (IP-level, persistent)
_OTHER_COOLDOWN_SEC = 60           # 1 min for transient errors (network, server)
_BLACKLIST_KEYWORD = "黑名单"


class BaoStockUnavailable(RuntimeError):
    """Raised when BaoStock circuit breaker is open."""


_CIRCUIT_LOCK = threading.Lock()
_CIRCUIT_REOPEN_AT: float | None = None  # monotonic timestamp when circuit re-closes

# baostock's socketutil uses a global singleton socket with no locking; without
# this mutex, concurrent asyncio.to_thread calls interleave send/recv and corrupt
# responses (manifests as IndexError: list index out of range in history.py).
_QUERY_LOCK = threading.Lock()

FIELD_SET = [
    "date",
    "code",
    "open",
    "high",
    "low",
    "close",
    "preclose",
    "volume",
    "amount",
    "turn",
    "pctChg",
]

ADJUST_FLAG_MAP = {
    "": "3",      # no adjustment
    "none": "3",
    "qfq": "2",   # pre-adjusted
    "hfq": "1",   # post-adjusted
}

# Shanghai-listed index codes that share the 000xxx prefix with SZ stocks.
# 000001 is intentionally excluded (ambiguous: 上证指数 vs 平安银行); pass
# "sh.000001" explicitly to query the index.
_KNOWN_SH_INDEX_CODES: set[str] = {
    "000016",  # 上证50
    "000300",  # 沪深300
    "000905",  # 中证500
    "000852",  # 中证1000
    "000010",  # 上证180
}


def _is_index_symbol(symbol: str) -> bool:
    """Return True for index codes (SH 000xxx indexes + SZ 399xxx indexes).

    - 399xxx (any prefix or bare) -> SZ index
    - Known SH index codes (000300 etc.) -> SH index
    - sh.000xxx (explicit SH prefix on 000xxx) -> SH index (covers 000001 上证指数)
    - Bare 000001 is treated as the stock 平安银行 (ambiguous, default stock)
    """
    s = symbol.strip().lower()
    if s.startswith("sh."):
        code = s[3:]
        return code in _KNOWN_SH_INDEX_CODES or code.startswith("000")
    if s.startswith("sz."):
        code = s[3:]
        return code.startswith("399")
    return s in _KNOWN_SH_INDEX_CODES or s.startswith("399")


def _logout() -> None:
    global _LOGGED_IN
    with _LOGIN_LOCK:
        if not _LOGGED_IN:
            return
        try:
            bs.logout()
            logger.info("BaoStock session closed.")
        finally:
            _LOGGED_IN = False


def _open_circuit(error_msg: str) -> None:
    """Open the circuit breaker with cooldown scaled by error type."""
    global _CIRCUIT_REOPEN_AT
    msg = error_msg or ""
    cooldown = _BLACKLIST_COOLDOWN_SEC if _BLACKLIST_KEYWORD in msg else _OTHER_COOLDOWN_SEC
    with _CIRCUIT_LOCK:
        _CIRCUIT_REOPEN_AT = time.monotonic() + cooldown
    logger.warning(
        "BaoStock circuit breaker opened for %d sec (reason: %s)",
        cooldown, msg,
    )


def _is_circuit_open() -> bool:
    """Return True if circuit is currently open. Lazily clears expired state."""
    global _CIRCUIT_REOPEN_AT
    with _CIRCUIT_LOCK:
        if _CIRCUIT_REOPEN_AT is None:
            return False
        if time.monotonic() >= _CIRCUIT_REOPEN_AT:
            _CIRCUIT_REOPEN_AT = None
            return False
        return True


def reset_circuit_breaker() -> None:
    """Test/admin hook: clear circuit breaker state immediately."""
    global _CIRCUIT_REOPEN_AT
    with _CIRCUIT_LOCK:
        _CIRCUIT_REOPEN_AT = None


def ensure_login() -> None:
    global _LOGGED_IN
    with _LOGIN_LOCK:
        if _LOGGED_IN:
            return
        if _is_circuit_open():
            raise BaoStockUnavailable("BaoStock circuit breaker open")
        rs = bs.login()
        if rs.error_code != "0":
            _open_circuit(rs.error_msg or "")
            raise RuntimeError(f"BaoStock login failed: {rs.error_msg}")
        _LOGGED_IN = True
        logger.info("BaoStock login successful.")
        atexit.register(_logout)


def format_symbol(symbol: str) -> str:
    symbol = symbol.strip()
    lowered = symbol.lower()
    if lowered.startswith("sh.") or lowered.startswith("sz."):
        return lowered
    if symbol in _KNOWN_SH_INDEX_CODES:
        return f"sh.{symbol}"
    if symbol.startswith(("6", "9")):
        return f"sh.{symbol}"
    return f"sz.{symbol}"


def _coerce_dates(value) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    return str(value)


def query_history_k_data_plus(
    symbol: str,
    start_date: datetime | str,
    end_date: datetime | str,
    adjust: str = "qfq",
) -> pd.DataFrame:
    ensure_login()
    bs_symbol = format_symbol(symbol)
    start = _coerce_dates(start_date)
    end = _coerce_dates(end_date)
    adjust_flag = ADJUST_FLAG_MAP.get(adjust.lower() if adjust else "", "2")

    fields = ",".join(FIELD_SET)
    with _QUERY_LOCK:
        rs = bs.query_history_k_data_plus(
            bs_symbol,
            fields,
            start_date=start,
            end_date=end,
            frequency="d",
            adjustflag=adjust_flag,
        )
        if rs.error_code == "10001001":  # not logged in
            _logout()
            ensure_login()
            rs = bs.query_history_k_data_plus(
                bs_symbol,
                fields,
                start_date=start,
                end_date=end,
                frequency="d",
                adjustflag=adjust_flag,
            )
        if rs.error_code != "0":
            raise RuntimeError(f"BaoStock query failed[{rs.error_code}]: {rs.error_msg}")

        rows: List[List[str]] = []
        while rs.error_code == "0" and rs.next():
            rows.append(rs.get_row_data())

    df = pd.DataFrame(rows, columns=FIELD_SET)
    return df


def query_trade_dates(start_date: datetime | str, end_date: datetime | str) -> pd.DataFrame:
    ensure_login()
    start = _coerce_dates(start_date)
    end = _coerce_dates(end_date)
    with _QUERY_LOCK:
        rs = bs.query_trade_dates(start_date=start, end_date=end)
        if rs.error_code == "10001001":  # not logged in
            _logout()
            ensure_login()
            rs = bs.query_trade_dates(start_date=start, end_date=end)
        if rs.error_code != "0":
            raise RuntimeError(f"BaoStock trade date query failed[{rs.error_code}]: {rs.error_msg}")
        rows: List[List[str]] = []
        while rs.error_code == "0" and rs.next():
            rows.append(rs.get_row_data())
    if not rows:
        return pd.DataFrame(columns=["calendar_date", "is_trading_day"])
    df = pd.DataFrame(rows, columns=rs.fields)
    return df


def query_stock_basic(code: str) -> pd.DataFrame:
    ensure_login()
    with _QUERY_LOCK:
        rs = bs.query_stock_basic(code=code)
        if rs.error_code == "10001001":  # not logged in
            _logout()
            ensure_login()
            rs = bs.query_stock_basic(code=code)
        if rs.error_code != "0":
            raise RuntimeError(f"BaoStock stock basic query failed[{rs.error_code}]: {rs.error_msg}")

        rows: List[List[str]] = []
        while rs.error_code == "0" and rs.next():
            rows.append(rs.get_row_data())
    if not rows:
        return pd.DataFrame(columns=rs.fields)
    df = pd.DataFrame(rows, columns=rs.fields)
    return df
