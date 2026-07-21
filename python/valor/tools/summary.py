"""Summary builders for market_data node.

These helpers produce compact, frontend-friendly summaries of raw price
history and financial data. The full ``prices`` list and ``financial_*``
dicts stay in ``state.data`` for downstream agents (technicals,
risk_manager, fundamentals, valuation) to consume, but the summaries are
what gets serialized into SSE events and the SQLite persistence layer -
keeping wire/DB payload small without losing the information the UI
actually displays.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Coerce ``value`` to float, returning ``default`` on failure/NaN."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(f) or math.isinf(f):
        return default
    return f


def _fmt_date(value: Any) -> str:
    """Normalize date-like value to ``YYYY-MM-DD`` string."""
    if value is None:
        return ""
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, str):
        return value[:10]
    try:
        return pd.Timestamp(value).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return str(value)[:10]


def _monthly_resample(df: pd.DataFrame) -> list[dict]:
    """Aggregate daily OHLCV to monthly candles, return as list of dicts.

    Each month maps to one record with ``date`` (YYYY-MM-DD-01),
    ``open`` (first), ``high`` (max), ``low`` (min), ``close`` (last),
    ``volume`` (sum). Returns empty list if ``df`` is empty or lacks
    required columns.
    """
    if df.empty or "close" not in df.columns:
        return []
    needed = ["date", "open", "high", "low", "close", "volume"]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        return []
    work = df[needed].copy()
    work["date"] = pd.to_datetime(work["date"], errors="coerce")
    work = work.dropna(subset=["date"]).set_index("date")
    if work.empty:
        return []
    monthly = work.resample("MS").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna(subset=["close"])
    records: list[dict] = []
    for ts, row in monthly.iterrows():
        records.append({
            "date": ts.strftime("%Y-%m-%d"),
            "open": _safe_float(row["open"]),
            "high": _safe_float(row["high"]),
            "low": _safe_float(row["low"]),
            "close": _safe_float(row["close"]),
            "volume": _safe_float(row["volume"]),
        })
    return records


def build_prices_summary(
    prices_df: pd.DataFrame,
    start_date: str,
    end_date: str,
) -> dict:
    """Build a compact summary of daily K-line data.

    Returns a dict with:
      - ``recent_5d``: last 5 trading days OHLCV (list of dict)
      - ``monthly_agg``: last 12 monthly candles (list of dict)
      - ``statistics``: highest/lowest/avg_close/annualized_volatility/
        ytd_change/avg_volume (highest/lowest include the date)
      - ``time_range``: {start, end, trading_days}

    Empty DataFrame yields a dict with empty lists and zeroed stats so
    downstream consumers don't need to special-case missing data.
    """
    empty_summary: dict = {
        "recent_5d": [],
        "monthly_agg": [],
        "statistics": {
            "highest": {"value": 0.0, "date": ""},
            "lowest": {"value": 0.0, "date": ""},
            "avg_close": 0.0,
            "annualized_volatility": 0.0,
            "ytd_change": 0.0,
            "avg_volume": 0.0,
        },
        "time_range": {
            "start": start_date,
            "end": end_date,
            "trading_days": 0,
        },
    }
    if prices_df is None or prices_df.empty:
        return empty_summary

    df = prices_df
    for col in ("close", "high", "low", "volume"):
        if col not in df.columns:
            return empty_summary

    # Recent 5 trading days
    recent_cols = [c for c in ("date", "open", "high", "low", "close", "volume") if c in df.columns]
    recent_5d = [
        {
            "date": _fmt_date(row.get("date")),
            "open": _safe_float(row.get("open")),
            "high": _safe_float(row.get("high")),
            "low": _safe_float(row.get("low")),
            "close": _safe_float(row.get("close")),
            "volume": _safe_float(row.get("volume")),
        }
        for _, row in df[recent_cols].tail(5).iterrows()
    ]

    # Monthly aggregation (last 12 months)
    monthly_agg = _monthly_resample(df)[-12:]

    # Statistics
    highs = df["high"].dropna()
    lows = df["low"].dropna()
    closes = df["close"].dropna()
    volumes = df["volume"].dropna()

    highest = {"value": 0.0, "date": ""}
    if not highs.empty:
        idx = highs.idxmax()
        highest = {
            "value": _safe_float(highs.loc[idx]),
            "date": _fmt_date(df.loc[idx, "date"]) if "date" in df.columns else "",
        }

    lowest = {"value": 0.0, "date": ""}
    if not lows.empty:
        idx = lows.idxmin()
        lowest = {
            "value": _safe_float(lows.loc[idx]),
            "date": _fmt_date(df.loc[idx, "date"]) if "date" in df.columns else "",
        }

    avg_close = _safe_float(closes.mean()) if not closes.empty else 0.0
    avg_volume = _safe_float(volumes.mean()) if not volumes.empty else 0.0

    if len(closes) >= 2:
        returns = closes.pct_change().dropna()
        annualized_volatility = _safe_float(returns.std() * (252 ** 0.5)) if not returns.empty else 0.0
        ytd_change = _safe_float(closes.iloc[-1] / closes.iloc[0] - 1)
    else:
        annualized_volatility = 0.0
        ytd_change = 0.0

    return {
        "recent_5d": recent_5d,
        "monthly_agg": monthly_agg,
        "statistics": {
            "highest": highest,
            "lowest": lowest,
            "avg_close": avg_close,
            "annualized_volatility": annualized_volatility,
            "ytd_change": ytd_change,
            "avg_volume": avg_volume,
        },
        "time_range": {
            "start": start_date,
            "end": end_date,
            "trading_days": int(len(df)),
        },
    }


def build_financial_summary(
    financial_metrics: list | dict,
    financial_line_items: list | dict,
) -> dict:
    """Extract a flat dict of key financial numbers for UI display.

    Pulls ROE / margins / growth / PE / PB / D/E / current ratio from
    ``financial_metrics[0]`` and revenue / net_income / free_cash_flow
    from ``financial_line_items[0]``. Missing values default to 0.0;
    empty input yields an empty dict.
    """
    summary: dict = {}
    if not financial_metrics:
        return summary

    metrics = (
        financial_metrics[0]
        if isinstance(financial_metrics, list)
        else financial_metrics
    )
    if not isinstance(metrics, dict):
        return summary

    field_map = [
        "return_on_equity",
        "net_margin",
        "operating_margin",
        "revenue_growth",
        "earnings_growth",
        "book_value_growth",
        "current_ratio",
        "debt_to_equity",
        "free_cash_flow_per_share",
        "earnings_per_share",
        "pe_ratio",
        "price_to_book",
        "price_to_sales",
        "dividend_yield",
        "book_value_per_share",
        "payout_ratio",
    ]
    for field in field_map:
        if field in metrics:
            summary[field] = _safe_float(metrics.get(field))

    if financial_line_items:
        line_items = (
            financial_line_items[0]
            if isinstance(financial_line_items, list)
            else financial_line_items
        )
        if isinstance(line_items, dict):
            for field in ("revenue", "net_income", "free_cash_flow",
                          "depreciation_and_amortization", "capital_expenditure"):
                if field in line_items:
                    summary[field] = _safe_float(line_items.get(field))

    return summary
