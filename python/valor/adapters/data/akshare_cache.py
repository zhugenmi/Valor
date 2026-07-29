"""Cached market data helpers backed by SQLite."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import json
from pathlib import Path
import os
import time
from typing import Dict, List, Optional
from typing import Sequence, Tuple

import akshare as ak
import pandas as pd

from valor.adapters.data.sqlite_cache import AkshareSQLiteCache
from valor.network.proxy_manager import ProxyManager
from valor.adapters.data.baostock_client import (
    BaoStockUnavailable,
    _is_index_symbol,
    query_history_k_data_plus,
    query_trade_dates,
)
from valor.utils.logging_config import setup_logger

# Column name constants (use unicode escapes to avoid encoding glitches)
COL_CODE = "\u4ee3\u7801"
COL_NAME = "\u540d\u79f0"
COL_DATE = "\u65e5\u671f"
COL_REPORT_DATE = "\u62a5\u544a\u65e5"
COL_REPORT_TYPE = "\u62a5\u8868\u7c7b\u578b"
COL_KEYWORD = "\u5173\u952e\u8bcd"
COL_PUBLISH_TIME = "\u53d1\u5e03\u65f6\u95f4"
COL_HEADLINE = "\u65b0\u95fb\u6807\u9898"
COL_CACHE_DATE = "\u7f13\u5b58\u65e5\u671f"
COL_ADJUST_TYPE = "\u590d\u6743\u7c7b\u578b"
COL_TRADE_DATE = "trade_date"
COL_INDUSTRY = "\u884c\u4e1a"

BASE_DIR = Path(__file__).resolve().parents[2]
_default_cache_path = BASE_DIR / "data" / "market_data_cache.db"
CACHE_PATH = Path(os.getenv("MARKET_CACHE_DB_PATH", str(_default_cache_path)))
HISTORY_TABLE = "baostock_history_k"
STOCK_NEWS_EM_TABLE = "stock_news_em_daily"
SPOT_TABLE = "stock_bid_ask_em"
VALUATION_TABLE = "stock_zh_valuation_baidu"
DIVIDEND_TABLE = "stock_history_dividend_detail"

# Map stock_bid_ask_em item labels to stock_zh_a_spot_em column names so
# downstream consumers (golden fixtures, adapters) keep seeing the same shape.
_BID_ASK_FIELD_MAP = {
    "最新": "最新价",
    "涨跌": "涨跌额",
    "涨幅": "涨跌幅",
    "总手": "成交量",
    "金额": "成交额",
    "换手": "换手率",
    "量比": "量比",
    "均价": "均价",
}

logger = setup_logger("akshare_cache")
cache = AkshareSQLiteCache(CACHE_PATH)
proxy_manager = ProxyManager.from_env(logger=logger)

# Dedicated proxy for realtime spot quotes: fail fast (1 attempt) since the caller
# can fall back to daily history. 3 retries on a flaky connection waste ~3s per ticker.
_spot_proxy = ProxyManager(
    proxies=["direct"],
    max_attempts=1,
    base_delay=0.5,
    max_delay=1.0,
    jitter=0.1,
    logger=logger,
)

# In-memory failure cache: prevents repeated retry storms on the same ticker
# within a short window (e.g. across list_portfolios + get_analytics calls).
_failure_cache: dict[str, float] = {}
FAILURE_CACHE_TTL = 60  # seconds


def _log_cache_hit(label: str, symbol: str, rows: int) -> None:
    logger.info("📦 [cache] %s 命中，标的=%s，行数=%d", label, symbol, rows)


def _log_cache_upsert(label: str, symbol: str, rows: int, extra: str = "") -> None:
    suffix = f"（{extra}" if extra else ""
    logger.info("🆕 [cache] %s 写入完成，标的=%s，新增/更新行数=%d%s", label, symbol, rows, suffix)


def _call_with_retry(func, label: str):
    try:
        return proxy_manager.run(func, label)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"AkShare {label} error: {exc}")
        return None


def _call_spot_quote(symbol: str):
    """Call stock_bid_ask_em with minimal retries — fail fast since the caller falls back to daily history."""
    try:
        return _spot_proxy.run(lambda: ak.stock_bid_ask_em(symbol=symbol), SPOT_TABLE)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"AkShare {SPOT_TABLE} error (falling back to daily history): {exc}")
        return None


def _drop_cache_columns(df: pd.DataFrame) -> pd.DataFrame:
    return df.drop(columns=["缓存时间"], errors="ignore")


def _records_to_df(records: List[Dict]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    return _drop_cache_columns(df)


def _resolve_exchange_symbol(symbol: str) -> str:
    cleaned = symbol.strip()
    lowered = cleaned.lower()
    if lowered.startswith(("sh", "sz")):
        return lowered
    if cleaned.startswith(("6", "9")):
        return f"sh{cleaned}"
    return f"sz{cleaned}"


def is_market_open(now: Optional[datetime] = None) -> bool:
    """Rough A-share trading-hours check: Mon-Fri 09:25-11:30, 13:00-15:00.

    Intentionally avoids network lookups (trade calendar) so it's cheap to call
    on every spot quote. Public holidays that fall on a weekday will still cause
    one cache miss per ticker that day - acceptable, since the 10-minute TTL
    caps the redundant calls and the next call re-populates the cache.
    """
    now = now or datetime.now()
    if now.weekday() >= 5:  # Sat=5, Sun=6
        return False
    hhmm = now.hour * 100 + now.minute
    return (925 <= hhmm <= 1130) or (1300 <= hhmm <= 1500)


def get_stock_spot_row(symbol: str, ttl_seconds: int = 600) -> Optional[pd.Series]:
    # When the market is closed the spot price is final for the day - extend
    # the TTL to 24h so we don't re-hit AkShare every 10 minutes after close
    # or over the weekend.
    if not is_market_open():
        ttl_seconds = max(ttl_seconds, 86400)
    # Check in-memory failure cache — avoids repeated 3-second retry storms
    # on the same ticker across multiple API calls (e.g. list + analytics).
    fail_ts = _failure_cache.get(symbol)
    if fail_ts is not None and (time.monotonic() - fail_ts) < FAILURE_CACHE_TTL:
        return None

    cached = cache.fetch_records(
        table=SPOT_TABLE,
        filters={COL_CODE: symbol},
        ttl_seconds=ttl_seconds,
        order_by='"缓存时间" DESC',
        limit=1,
    )
    if cached:
        _log_cache_hit(SPOT_TABLE, symbol, len(cached))
        row = cached[0].copy()
        row.pop("缓存时间", None)
        return pd.Series(row)

    # Outside trading hours the spot endpoint either fails or returns a stale
    # intraday price that disagrees with the daily close. Skip the network call
    # entirely so callers fall back to daily history (yesterday's close).
    if not is_market_open():
        return None

    df = _call_spot_quote(symbol)
    if df is None or df.empty:
        _failure_cache[symbol] = time.monotonic()
        return None

    row_dict = {COL_CODE: symbol}
    for _, r in df.iterrows():
        item = str(r["item"])
        if item in _BID_ASK_FIELD_MAP:
            row_dict[_BID_ASK_FIELD_MAP[item]] = r["value"]

    if "最新价" not in row_dict:
        _failure_cache[symbol] = time.monotonic()
        return None

    cache.upsert_records(
        SPOT_TABLE,
        [row_dict],
        key_columns=[COL_CODE],
    )
    _log_cache_upsert(SPOT_TABLE, symbol, 1)
    return pd.Series(row_dict)


# ---------------------------------------------------------------------------
# Valuation indicators (PE-TTM / PB / market_cap) from Baidu Gushitong
# ---------------------------------------------------------------------------


def _fetch_valuation_baidu(symbol: str, indicator: str) -> pd.DataFrame:
    """Call stock_zh_valuation_baidu for one indicator; return empty df on failure."""
    try:
        df = _call_with_retry(
            lambda: ak.stock_zh_valuation_baidu(
                symbol=symbol, indicator=indicator, period="近一年"
            ),
            f"stock_zh_valuation_baidu[{indicator}]",
        )
        return df if df is not None else pd.DataFrame()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"stock_zh_valuation_baidu[{indicator}] error: {exc}")
        return pd.DataFrame()


def get_valuation_indicator(symbol: str, ttl_seconds: int = 24 * 3600) -> dict:
    """获取 PE-TTM / PB / 总市值 / 股价(百度股市通,每日更新)。

    Returns dict with keys: date, pe_ttm, pb, market_cap (元), price.
    失败返回空 dict,调用方负责 fallback。
    """
    fail_key = f"val_{symbol}"
    fail_ts = _failure_cache.get(fail_key)
    if fail_ts is not None and (time.monotonic() - fail_ts) < FAILURE_CACHE_TTL:
        return {}

    cached = cache.fetch_records(
        table=VALUATION_TABLE,
        filters={COL_CODE: symbol},
        ttl_seconds=ttl_seconds,
        order_by='"缓存时间" DESC',
        limit=1,
    )
    if cached:
        _log_cache_hit(VALUATION_TABLE, symbol, 1)
        row = cached[0].copy()
        row.pop("缓存时间", None)
        return row

    market_cap_series = _fetch_valuation_baidu(symbol, "总市值")
    pe_series = _fetch_valuation_baidu(symbol, "市盈率(TTM)")
    pb_series = _fetch_valuation_baidu(symbol, "市净率")

    if market_cap_series.empty or pe_series.empty or pb_series.empty:
        _failure_cache[fail_key] = time.monotonic()
        return {}

    def _last_value(df: pd.DataFrame) -> float:
        try:
            return float(pd.to_numeric(df.iloc[-1]["value"], errors="coerce"))
        except (KeyError, IndexError, ValueError, TypeError):
            return 0.0

    market_cap_yi = _last_value(market_cap_series)
    pe_ttm = _last_value(pe_series)
    pb = _last_value(pb_series)
    date_str = str(market_cap_series.iloc[-1].get("date", ""))

    # 百度接口返回单位: 亿元,转换为元
    market_cap = market_cap_yi * 1e8

    # 从 BaoStock 历史缓存取最新收盘价(代价小,缓存命中)
    price = 0.0
    try:
        end = datetime.now()
        start = end - timedelta(days=10)
        price_df = get_price_history_df(symbol, start, end, adjust="qfq")
        if not price_df.empty:
            price = float(pd.to_numeric(price_df["close"].iloc[-1], errors="coerce"))
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"get_valuation_indicator: 获取最新股价失败: {exc}")

    record = {
        COL_CODE: symbol,
        "date": date_str,
        "pe_ttm": pe_ttm,
        "pb": pb,
        "market_cap": market_cap,
        "price": price,
    }
    cache.upsert_records(VALUATION_TABLE, [record], key_columns=[COL_CODE])
    _log_cache_upsert(VALUATION_TABLE, symbol, 1)
    return record


def get_dividend_yield(
    symbol: str,
    current_price: float,
    ttl_seconds: int = 30 * 24 * 3600,
) -> float:
    """计算近12个月股息率(基于除权除息日)。

    股息率 = 近12个月每股分红 / 当前股价
    每股分红 = sum(近12个月"派息") / 10  (新浪"派息"字段是每10股金额)
    current_price <= 0 或无分红记录返回 0.0。
    """
    if current_price <= 0:
        return 0.0

    cached = cache.fetch_records(
        table=DIVIDEND_TABLE,
        filters={COL_CODE: symbol},
        ttl_seconds=ttl_seconds,
        order_by='"公告日期" DESC',
    )
    df = _records_to_df(cached) if cached else pd.DataFrame()

    if df.empty:
        try:
            raw = _call_with_retry(
                lambda: ak.stock_history_dividend_detail(symbol=symbol, indicator="分红"),
                "stock_history_dividend_detail",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"stock_history_dividend_detail error: {exc}")
            return 0.0
        if raw is None or raw.empty:
            return 0.0
        raw = raw.copy()
        raw[COL_CODE] = symbol
        cache.upsert_records(
            DIVIDEND_TABLE,
            raw.to_dict("records"),
            key_columns=[COL_CODE, "公告日期"],
        )
        _log_cache_upsert(DIVIDEND_TABLE, symbol, len(raw))
        df = raw

    if df.empty or "除权除息日" not in df.columns:
        return 0.0

    work = df.copy()
    work["除权除息日"] = pd.to_datetime(work["除权除息日"], errors="coerce")
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=365)
    recent = work[work["除权除息日"] >= cutoff]
    if recent.empty:
        return 0.0

    total_cash = pd.to_numeric(recent["派息"], errors="coerce").fillna(0).sum()
    per_share = total_cash / 10.0
    return per_share / current_price if current_price > 0 else 0.0


def _indicators_has_new_period(cached_records: list[dict]) -> bool:
    """缓存里最新一条 日期 对应的季度，是否已经有下一季度应披露。"""
    if not cached_records:
        return False
    df = _records_to_df(cached_records)
    if df.empty or COL_DATE not in df.columns:
        return False
    try:
        latest_date = pd.to_datetime(df[COL_DATE].max()).date()
    except Exception:
        return False
    from valor.adapters.data.report_calendar import should_refresh_reports

    return should_refresh_reports(latest_date)


def get_financial_indicators(
    symbol: str,
    start_year: str | None = None,
    ttl_seconds: int = 24 * 3600,  # 保留兼容性，未使用
    force_refresh: bool = False,
) -> pd.DataFrame:
    # 财务指标缓存改为"无 TTL 常驻"；ttl_seconds 参数仅保留兼容性
    if force_refresh:
        logger.info("🔄 强制刷新财务指标缓存: %s", symbol)

    cached = [] if force_refresh else cache.fetch_records(
        table="stock_financial_analysis_indicator",
        filters={COL_CODE: symbol},
        order_by=f'"{COL_DATE}" DESC',
    )

    # 推算 start_year：有缓存用 MAX(日期).year（兼顾修订），无缓存用传入值或近 5 年
    if cached:
        cached_df = _records_to_df(cached)
        try:
            latest_year = str(pd.to_datetime(cached_df[COL_DATE].max()).year)
        except Exception:
            latest_year = start_year or str(datetime.now().year - 5)
        effective_start_year = latest_year
    else:
        effective_start_year = start_year or str(datetime.now().year - 5)

    need_fetch = (
        not cached
        or force_refresh
        or _indicators_has_new_period(cached)
    )

    if not need_fetch:
        _log_cache_hit("stock_financial_analysis_indicator", symbol, len(cached))
        return cached_df  # type: ignore[return-value]

    df = _call_with_retry(
        lambda: ak.stock_financial_analysis_indicator(
            symbol=symbol, start_year=effective_start_year
        ),
        "stock_financial_analysis_indicator",
    )
    if df is None or df.empty:
        if cached:
            logger.warning(
                "⚠️ 远程拉取财报指标失败，降级返回缓存: %s (缓存行数=%d)",
                symbol, len(cached),
            )
            return cached_df  # type: ignore[return-value]
        return pd.DataFrame()

    df[COL_CODE] = symbol
    cache.upsert_records(
        "stock_financial_analysis_indicator",
        df.to_dict("records"),
        key_columns=[COL_CODE, COL_DATE],
    )
    _log_cache_upsert("stock_financial_analysis_indicator", symbol, len(df))

    if cached:
        combined = pd.concat([cached_df, df], ignore_index=True)
        combined = combined.drop_duplicates(subset=[COL_CODE, COL_DATE], keep="last")
        combined[COL_DATE] = pd.to_datetime(combined[COL_DATE])
        return combined.sort_values(COL_DATE, ascending=False)
    return df


def _parse_ths_amount(value) -> float:
    """解析同花顺金额字符串: '281.54亿' -> 2.8154e10, '5931.07万' -> 5.93107e7, 'False'/'--' -> 0.0"""
    if value is None:
        return 0.0
    s = str(value).strip()
    if not s or s in {"False", "--", "nan", "NaN", "None"}:
        return 0.0
    multiplier = 1.0
    if s.endswith("亿"):
        multiplier = 1e8
        s = s[:-1]
    elif s.endswith("万"):
        multiplier = 1e4
        s = s[:-1]
    try:
        return float(s) * multiplier
    except (ValueError, TypeError):
        return 0.0


# 同花顺利润表字段名(带"一、"/"三、"/"五、"前缀) -> 新浪字段名
# 资产负债表和现金流量表字段名与新浪完全一致,无需映射
_THS_INCOME_FIELD_MAP = {
    "一、营业总收入": "营业总收入",
    "其中：营业收入": "营业收入",
    "二、营业总成本": "营业总成本",
    "其中：营业成本": "营业成本",
    "三、营业利润": "营业利润",
    "四、利润总额": "利润总额",
    "五、净利润": "净利润",
    "（一）基本每股收益": "基本每股收益",
    "（二）稀释每股收益": "稀释每股收益",
}

_THS_REPORT_FUNC_MAP = {
    "资产负债表": "stock_financial_debt_ths",
    "利润表": "stock_financial_benefit_ths",
    "现金流量表": "stock_financial_cash_ths",
}


def _fetch_financial_report_ths(symbol: str, report_type: str) -> pd.DataFrame:
    """用同花顺接口拉取财务报表,字段映射到与新浪相同的中文键名。

    数据格式:同花顺返回"亿"/"万"字符串,需解析为元数值。
    报告期字段:同花顺用"报告期",新浪用"报告日",统一为"报告日"(YYYY-MM-DD)。
    利润表:同花顺字段名带"一、"/"三、"/"五、"前缀,需映射。
    资产负债表/现金流量表:字段名与新浪完全一致,无需映射。
    """
    ak_func_name = _THS_REPORT_FUNC_MAP.get(report_type)
    if not ak_func_name:
        return pd.DataFrame()

    ak_func = getattr(ak, ak_func_name, None)
    if ak_func is None:
        logger.warning("AkShare 不支持接口: %s", ak_func_name)
        return pd.DataFrame()

    df = _call_with_retry(
        lambda: ak_func(symbol=symbol, indicator="按报告期"),
        ak_func_name,
    )
    if df is None or df.empty:
        return pd.DataFrame()

    # 利润表字段映射
    if report_type == "利润表":
        df = df.rename(columns={k: v for k, v in _THS_INCOME_FIELD_MAP.items() if k in df.columns})

    # 报告期 -> 报告日(格式 YYYY-MM-DD,与新浪一致)
    if "报告期" in df.columns:
        df[COL_REPORT_DATE] = pd.to_datetime(df["报告期"]).dt.strftime("%Y-%m-%d")
        df = df.drop(columns=["报告期"])

    # 数值列解析:"亿"/"万"字符串 -> 元(float)
    for col in df.columns:
        if col in (COL_REPORT_DATE, COL_CODE, COL_REPORT_TYPE):
            continue
        df[col] = df[col].apply(_parse_ths_amount)

    df[COL_CODE] = symbol
    df[COL_REPORT_TYPE] = report_type
    return df


def get_financial_report(
    symbol: str,
    report_type: str,
    ttl_seconds: int = 7 * 24 * 3600,  # 保留兼容性，未使用
    force_refresh: bool = False,
) -> pd.DataFrame:
    # 财务报表缓存改为"无 TTL 常驻"；ttl_seconds 参数仅保留兼容性
    if force_refresh:
        logger.info("🔄 强制刷新财务报表缓存: %s %s", symbol, report_type)

    cached = [] if force_refresh else cache.fetch_records(
        table="stock_financial_report_sina",
        filters={COL_CODE: symbol, COL_REPORT_TYPE: report_type},
        order_by=f'"{COL_REPORT_DATE}" DESC',
    )

    cached_df = _records_to_df(cached) if cached else pd.DataFrame()
    latest_report_date = None
    if not cached_df.empty and COL_REPORT_DATE in cached_df.columns:
        try:
            latest_report_date = pd.to_datetime(
                cached_df[COL_REPORT_DATE].max()
            ).date()
        except Exception:
            latest_report_date = None

    from valor.adapters.data.report_calendar import should_refresh_reports

    need_fetch = force_refresh or should_refresh_reports(latest_report_date)

    if not need_fetch:
        _log_cache_hit(f"stock_financial_report_sina[{report_type}]", symbol, len(cached))
        return cached_df

    exchange_symbol = _resolve_exchange_symbol(symbol)
    df = _call_with_retry(
        lambda: ak.stock_financial_report_sina(stock=exchange_symbol, symbol=report_type),
        "stock_financial_report_sina",
    )
    if df is None or df.empty:
        logger.warning(
            "⚠️ 新浪财报报表失败，尝试同花顺 fallback: %s %s",
            symbol, report_type,
        )
        df = _fetch_financial_report_ths(symbol, report_type)
    if df is None or df.empty:
        if cached:
            logger.warning(
                "⚠️ 新浪+同花顺均失败，降级返回缓存: %s %s (缓存行数=%d)",
                symbol, report_type, len(cached),
            )
            return cached_df
        return pd.DataFrame()

    if COL_REPORT_DATE in df.columns:
        df[COL_REPORT_DATE] = pd.to_datetime(df[COL_REPORT_DATE]).dt.strftime("%Y-%m-%d")
    df[COL_CODE] = symbol
    df[COL_REPORT_TYPE] = report_type
    cache.upsert_records(
        "stock_financial_report_sina",
        df.to_dict("records"),
        key_columns=[COL_CODE, COL_REPORT_TYPE, COL_REPORT_DATE],
    )
    _log_cache_upsert(f"stock_financial_report_sina[{report_type}]", symbol, len(df))

    if cached:
        combined = pd.concat([cached_df, df], ignore_index=True)
        combined = combined.drop_duplicates(
            subset=[COL_CODE, COL_REPORT_TYPE, COL_REPORT_DATE], keep="last"
        )
        combined[COL_REPORT_DATE] = pd.to_datetime(combined[COL_REPORT_DATE])
        return combined.sort_values(COL_REPORT_DATE, ascending=False)
    return df


def _exclude_today_if_before_close(
    days: Sequence[pd.Timestamp],
) -> list[pd.Timestamp]:
    """Before 15:00 the daily K-line for today isn't available yet; drop it."""
    if datetime.now().hour < 15:
        today_ts = pd.Timestamp(datetime.now().date()).normalize()
        return [d for d in days if pd.Timestamp(d).normalize() != today_ts]
    return list(days)


def _expected_trading_days(start_date: datetime, end_date: datetime) -> Sequence[pd.Timestamp]:
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    try:
        df = query_trade_dates(start_date, end_date)
        if df.empty:
            raise RuntimeError("query_trade_dates returned empty")
    except Exception as exc:
        logger.warning(
            "⚠️ query_trade_dates 失败，降级 akshare tool_trade_date_hist_sina: %s",
            exc,
        )
        try:
            trade_cal = _call_with_retry(
                lambda: ak.tool_trade_date_hist_sina(),
                "tool_trade_date_hist_sina",
            )
            if trade_cal is not None and not trade_cal.empty and "trade_date" in trade_cal.columns:
                all_dates = pd.to_datetime(trade_cal["trade_date"]).dt.normalize()
                start_ts = pd.Timestamp(start_date).normalize()
                end_ts = pd.Timestamp(end_date).normalize()
                mask = (all_dates >= start_ts) & (all_dates <= end_ts)
                return _exclude_today_if_before_close(all_dates.loc[mask].tolist())
        except Exception as exc2:
            logger.warning(
                "⚠️ akshare tool_trade_date_hist_sina 也失败，最后降级 bdate_range: %s",
                exc2,
            )
        return _exclude_today_if_before_close(pd.bdate_range(start=start_date, end=end_date))
    df["calendar_date"] = pd.to_datetime(df["calendar_date"])
    trading = df[df["is_trading_day"].astype(int) == 1]["calendar_date"].dt.normalize()
    return _exclude_today_if_before_close(trading.tolist())


def _missing_segments(
    expected_days: Sequence[pd.Timestamp],
    cached_days: Sequence[pd.Timestamp],
) -> List[Tuple[pd.Timestamp, pd.Timestamp]]:
    cached_set = {day.normalize() for day in cached_days}
    segments: List[Tuple[pd.Timestamp, pd.Timestamp]] = []
    seg_start: Optional[pd.Timestamp] = None
    seg_end: Optional[pd.Timestamp] = None
    for day in expected_days:
        normalized = day.normalize()
        if normalized not in cached_set:
            if seg_start is None:
                seg_start = day
            seg_end = day
        elif seg_start is not None:
            segments.append((seg_start, seg_end))
            seg_start = seg_end = None
    if seg_start is not None:
        segments.append((seg_start, seg_end or seg_start))
    return segments


def _prepare_history_frame(raw_df: pd.DataFrame, symbol: str, adjust: str) -> pd.DataFrame:
    if raw_df.empty:
        return pd.DataFrame()
    numeric_cols = ["open", "high", "low", "close", "preclose", "volume", "amount"]
    for col in numeric_cols:
        raw_df[col] = pd.to_numeric(raw_df[col], errors="coerce")
    raw_df["pct_change"] = pd.to_numeric(raw_df["pctChg"], errors="coerce") / 100.0
    raw_df["turnover"] = pd.to_numeric(raw_df["turn"], errors="coerce") / 100.0
    raw_df["change_amount"] = raw_df["close"] - raw_df["preclose"]
    base = raw_df["preclose"].replace(0, pd.NA)
    raw_df["amplitude"] = ((raw_df["high"] - raw_df["low"]) / base) * 100
    raw_df["amplitude"] = raw_df["amplitude"].fillna(0)
    raw_df["date"] = pd.to_datetime(raw_df["date"])
    raw_df["symbol"] = symbol
    raw_df["adjust_flag"] = adjust or ""
    columns = [
        "symbol",
        "adjust_flag",
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "amplitude",
        "pct_change",
        "change_amount",
        "turnover",
    ]
    return raw_df[columns]


# akshare stock_zh_a_hist column name -> internal name
_AKSHARE_KLINE_COLUMN_MAP = {
    "日期": "date",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "成交额": "amount",
    "振幅": "amplitude",
    "涨跌幅": "pctChg",
    "涨跌额": "change_amount",
    "换手率": "turn",
}


def _fetch_kline_via_akshare(
    symbol: str,
    start_date: str,
    end_date: str,
    adjust: str,
) -> pd.DataFrame:
    """Fetch daily K-line via akshare (East Money) as BaoStock fallback.

    Returns DataFrame with the same schema as _prepare_history_frame so the
    result can be cached in baostock_history_k and consumed downstream
    without branching on source.
    """
    adjust_norm = (adjust or "").lower()
    ak_adjust = {"qfq": "qfq", "hfq": "hfq", "": "", "none": ""}.get(adjust_norm, "qfq")

    # Indexes (000300 etc.) must use index_zh_a_hist; stock_zh_a_hist returns
    # empty for index codes. index_zh_a_hist has no adjust parameter.
    if _is_index_symbol(symbol):
        df = _call_with_retry(
            lambda: ak.index_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
            ),
            "index_zh_a_hist",
        )
    else:
        df = _call_with_retry(
            lambda: ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                adjust=ak_adjust,
            ),
            "stock_zh_a_hist",
        )
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.rename(columns={k: v for k, v in _AKSHARE_KLINE_COLUMN_MAP.items() if k in df.columns})

    numeric_cols = ["open", "high", "low", "close", "volume", "amount",
                    "pctChg", "turn", "amplitude", "change_amount"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    # akshare doesn't return preclose; derive from prior close for amplitude/change_amount
    df["preclose"] = df["close"].shift(1)
    preclose_na = df["preclose"].isna()
    if preclose_na.any():
        df.loc[preclose_na, "preclose"] = df.loc[preclose_na, "open"]

    # change_amount: use akshare's value if present, else compute from close-preclose
    if "change_amount" not in df.columns or df["change_amount"].isna().all():
        df["change_amount"] = df["close"] - df["preclose"]

    # amplitude: percent, matches _prepare_history_frame ((high-low)/preclose * 100)
    if "amplitude" not in df.columns or df["amplitude"].isna().all():
        base = df["preclose"].replace(0, pd.NA)
        df["amplitude"] = ((df["high"] - df["low"]) / base * 100).fillna(0)

    result = pd.DataFrame({
        "symbol": symbol,
        "adjust_flag": adjust or "",
        "date": df["date"],
        "open": df.get("open", 0.0),
        "high": df.get("high", 0.0),
        "low": df.get("low", 0.0),
        "close": df.get("close", 0.0),
        # AkShare 成交量单位是"手",统一为"股"(* 100)与其他源对齐
        "volume": df.get("volume", 0.0) * 100,
        # AkShare 成交额单位已是"元",无需转换
        "amount": df.get("amount", 0.0),
        "amplitude": df["amplitude"].fillna(0),
        "pct_change": (df["pctChg"] / 100.0).fillna(0) if "pctChg" in df.columns else 0.0,
        "change_amount": df["change_amount"].fillna(0),
        "turnover": (df["turn"] / 100.0).fillna(0) if "turn" in df.columns else 0.0,
    })
    return result


def _get_tushare_client():
    """Lazily build a TushareClient; returns None if TUSHARE_TOKEN unset."""
    token = os.getenv("TUSHARE_TOKEN")
    if not token:
        return None
    from valor.adapters.data.tushare_client import TushareClient

    return TushareClient(token=token)


def _tushare_available() -> bool:
    return bool(os.getenv("TUSHARE_TOKEN"))


def _fetch_kline_via_tushare(
    symbol: str,
    start_date: str,
    end_date: str,
    adjust: str,
) -> pd.DataFrame:
    """Fetch daily K-line via Tushare ``daily`` as third-tier fallback.

    Tushare only provides unadjusted quotes on the basic tier, so
    ``adjust`` is ignored and ``adjust_flag`` is recorded as "".
    Returns DataFrame with the same schema as _prepare_history_frame.
    """
    from valor.adapters.data.tushare_client import TushareClient, TushareUnavailable
    from valor.adapters.data.unit_conversion import (
        build_unified_kline_df,
        compute_amplitude,
        pct_to_decimal,
        to_shares,
        to_yuan,
    )

    client = _get_tushare_client()
    if client is None or not client.available:
        logger.warning("Tushare 不可用(TUSHARE_TOKEN 未配置或初始化失败)")
        return pd.DataFrame()

    ts_code = TushareClient.to_ts_code(symbol)
    try:
        raw = client.query_daily(ts_code, start_date, end_date)
    except TushareUnavailable as exc:
        logger.warning("Tushare 限速或不可用: %s [%s -> %s] (%s)", symbol, start_date, end_date, exc)
        return pd.DataFrame()

    if raw is None or raw.empty:
        logger.warning("Tushare daily 返回空: %s [%s -> %s]", symbol, start_date, end_date)
        return pd.DataFrame()

    raw = raw.sort_values("trade_date").reset_index(drop=True)

    open_ = pd.to_numeric(raw.get("open"), errors="coerce").fillna(0.0)
    high = pd.to_numeric(raw.get("high"), errors="coerce").fillna(0.0)
    low = pd.to_numeric(raw.get("low"), errors="coerce").fillna(0.0)
    close = pd.to_numeric(raw.get("close"), errors="coerce").fillna(0.0)
    preclose = pd.to_numeric(raw.get("pre_close"), errors="coerce").fillna(0.0)
    change_amount = pd.to_numeric(raw.get("change"), errors="coerce").fillna(0.0)
    pct_change = raw["pct_chg"].apply(pct_to_decimal) if "pct_chg" in raw.columns else 0.0
    # Tushare vol 单位是"手",amount 单位是"千元";统一为"股"和"元"
    volume = raw["vol"].apply(to_shares) if "vol" in raw.columns else 0.0
    amount = raw["amount"].apply(to_yuan) if "amount" in raw.columns else 0.0
    amplitude = [
        compute_amplitude(h, lo, p)
        for h, lo, p in zip(high.tolist(), low.tolist(), preclose.tolist())
    ]

    return build_unified_kline_df(
        symbol=symbol,
        adjust="",
        date=raw["trade_date"],
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        amount=amount,
        amplitude=amplitude,
        pct_change=pct_change,
        change_amount=change_amount,
        turnover=[0.0] * len(raw),
    )


def _cache_history_rows(df: pd.DataFrame) -> None:
    if df.empty:
        return
    cache.upsert_records(
        HISTORY_TABLE,
        df.to_dict("records"),
        key_columns=["symbol", "adjust_flag", "date"],
    )
    _log_cache_upsert(HISTORY_TABLE, df.iloc[0]["symbol"], len(df))


def get_price_history_df(
    symbol: str,
    start_date: datetime,
    end_date: datetime,
    adjust: str = "qfq",
    ttl_seconds: Optional[int] = None,  # kept for backward compatibility, unused
    force_refresh: bool = False,
) -> pd.DataFrame:
    if force_refresh:
        logger.info("🔄 强制刷新历史K线缓存: %s", symbol)

    filters = {"symbol": symbol, "adjust_flag": adjust or ""}
    cached_records = [] if force_refresh else cache.fetch_records(
        table=HISTORY_TABLE,
        filters=filters,
        order_by='"date" ASC',
    )

    cached_frames: List[pd.DataFrame] = []
    cached_dates: List[pd.Timestamp] = []
    if cached_records:
        df_cached = _records_to_df(cached_records)
        if not df_cached.empty:
            df_cached["date"] = pd.to_datetime(df_cached["date"])
            cached_frames.append(df_cached)
            cached_dates = list(df_cached["date"].dt.normalize())

    expected_days = _expected_trading_days(start_date, end_date)
    missing_segments = _missing_segments(expected_days, cached_dates)
    if not missing_segments:
        logger.info(
            "📦 Price history cache satisfied for %s（%d 个交易日）",
            symbol,
            len(expected_days),
        )
    else:
        cached_normalized = {day.normalize() for day in cached_dates}
        missing_trading_days = sum(
            1 for day in expected_days if day.normalize() not in cached_normalized
        )
        logger.info(
            "🔄 Price history cache 缺少 %d 个交易日，共 %d 个区间，正在增量拉取 %s",
            missing_trading_days,
            len(missing_segments),
            symbol,
        )

    new_frames: List[pd.DataFrame] = []
    for seg_start, seg_end in missing_segments:
        start_str = seg_start.strftime("%Y-%m-%d")
        end_str = seg_end.strftime("%Y-%m-%d")
        prepared = pd.DataFrame()
        try:
            raw = query_history_k_data_plus(
                symbol=symbol,
                start_date=start_str,
                end_date=end_str,
                adjust=adjust,
            )
            prepared = _prepare_history_frame(raw, symbol, adjust)
        except (BaoStockUnavailable, RuntimeError, IndexError) as exc:
            logger.warning(
                "⚠️ BaoStock K线拉取失败，降级 akshare: %s [%s -> %s] (%s)",
                symbol, start_str, end_str, exc,
            )
            prepared = _fetch_kline_via_akshare(symbol, start_str, end_str, adjust)
            # Tushare 第三备选(需 TUSHARE_TOKEN 配置)
            if prepared.empty and _tushare_available():
                logger.warning(
                    "⚠️ AkShare K线也失败，降级 tushare: %s [%s -> %s]",
                    symbol, start_str, end_str,
                )
                prepared = _fetch_kline_via_tushare(symbol, start_str, end_str, adjust)

        if not prepared.empty:
            _cache_history_rows(prepared)
            new_frames.append(prepared)
        else:
            logger.warning(
                "⚠️ K线三源均失败: %s [%s -> %s]，跳过该段（已有缓存段仍可用）",
                symbol, start_str, end_str,
            )

    if not cached_frames and not new_frames:
        return pd.DataFrame()

    combined = pd.concat(cached_frames + new_frames, ignore_index=True)
    combined.drop_duplicates(subset=["symbol", "adjust_flag", "date"], keep="last", inplace=True)
    mask = (combined["date"] >= pd.to_datetime(start_date)) & (combined["date"] <= pd.to_datetime(end_date))
    result = combined.loc[mask].copy()
    result.sort_values("date", inplace=True)
    source_tag = "📊 数据来源: 缓存" if not new_frames else "📊 数据来源: 缓存+增量刷新"
    logger.info("%s，标的=%s，输出行数=%d", source_tag, symbol, len(result))
    return result

def _normalize_date_str(value: str) -> str:
    value = (value or "").strip()
    if len(value) >= 10 and value[4] == "-" and value[7] == "-":
        return value[:10]
    return value


def get_stock_news(
    symbol: str,
    *,
    date: Optional[str] = None,
    ttl_seconds: int = 2 * 3600,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    获取新闻并缓存到 SQLite。

    缓存 key（命中维度）按"标的 + 日期"进行过滤，避免跨日期误命中。
    - date=None：默认使用今天（UTC+0 的 date string），并应用 ttl_seconds
    - date=YYYY-MM-DD：按指定日期命中；历史日期不使用 TTL（视为稳定）
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    date_str = _normalize_date_str(date or today_str)
    effective_ttl = ttl_seconds if date is None or date_str == today_str else None

    if force_refresh:
        logger.info("🔄 强制刷新新闻缓存(stock_news_em): %s %s", symbol, date_str)

    if not force_refresh:
        cached = cache.fetch_records(
            table=STOCK_NEWS_EM_TABLE,
            filters={COL_KEYWORD: symbol, COL_CACHE_DATE: date_str},
            ttl_seconds=effective_ttl,
            limit=1,
        )
        if cached:
            _log_cache_hit(STOCK_NEWS_EM_TABLE, symbol, len(cached))
            record = dict(cached[0])
            news_json = record.get("news_json")
            if news_json:
                try:
                    records = json.loads(news_json)
                    return pd.DataFrame(records)
                except Exception:
                    return pd.DataFrame()

    df = _call_with_retry(lambda: ak.stock_news_em(symbol=symbol), "stock_news_em")
    if df is None:
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    df[COL_KEYWORD] = symbol
    # 为缓存命中增加"日期"维度
    if COL_PUBLISH_TIME in df.columns:
        df[COL_CACHE_DATE] = df[COL_PUBLISH_TIME].astype(str).str.slice(0, 10)
    else:
        df[COL_CACHE_DATE] = date_str

    # 只缓存目标日期的数据（避免把历史/其它日期混入当天 cache key）
    df = df[df[COL_CACHE_DATE] == date_str].copy()
    if df.empty:
        return pd.DataFrame()

    record = {
        COL_KEYWORD: symbol,
        COL_CACHE_DATE: date_str,
        "news_json": json.dumps(df.to_dict("records"), ensure_ascii=False),
        "news_count": len(df),
    }
    cache.upsert_records(
        STOCK_NEWS_EM_TABLE,
        [record],
        key_columns=[COL_KEYWORD, COL_CACHE_DATE],
    )
    _log_cache_upsert(STOCK_NEWS_EM_TABLE, symbol, len(df))
    return df


def get_latest_trading_day(today: Optional["date"] = None) -> "date":
    """Return the most recent A-share trading day on or before `today`.

    Looks back up to 30 calendar days to skip weekends/holidays.

    Source order (akshare first to avoid BaoStock's slow login):
    1. akshare ``tool_trade_date_hist_sina`` -- full trade calendar, no login.
    2. BaoStock ``query_trade_dates`` -- only when akshare fails.
    3. Most recent weekday -- last resort when both remote sources fail.
    """
    from datetime import date as _date, timedelta

    today = today or _date.today()
    start = today - timedelta(days=30)
    today_ts = pd.Timestamp(today).normalize()

    # 1. akshare 全历史交易日历（无需登录，快）
    try:
        trade_cal = _call_with_retry(
            lambda: ak.tool_trade_date_hist_sina(),
            "tool_trade_date_hist_sina",
        )
        if trade_cal is not None and not trade_cal.empty and "trade_date" in trade_cal.columns:
            all_dates = pd.to_datetime(trade_cal["trade_date"]).dt.normalize()
            valid = all_dates[all_dates <= today_ts]
            if not valid.empty:
                latest = valid.max()
                logger.debug("get_latest_trading_day via akshare: %s", latest.date())
                return latest.date()
            logger.warning("⚠️ akshare tool_trade_date_hist_sina 返回的交易日历中无 <= today 的日期")
        else:
            logger.warning("⚠️ akshare tool_trade_date_hist_sina 返回空，降级 BaoStock")
    except Exception as exc:  # noqa: BLE001
        logger.warning("⚠️ akshare tool_trade_date_hist_sina 异常，降级 BaoStock: %s", exc)

    # 2. BaoStock 降级（需要登录，慢）
    try:
        df = query_trade_dates(start, today)
        if df is None or df.empty:
            raise RuntimeError("query_trade_dates returned empty")
        df["calendar_date"] = pd.to_datetime(df["calendar_date"])
        trading = df[df["is_trading_day"].astype(int) == 1]["calendar_date"].dt.normalize()
        trading_days = sorted(trading.tolist())
        for day in reversed(trading_days):
            if day <= today_ts:
                logger.debug("get_latest_trading_day via BaoStock: %s", day.date())
                return day.date()
    except Exception as exc:  # noqa: BLE001
        logger.warning("⚠️ get_latest_trading_day BaoStock 也失败，降级最近工作日: %s", exc)

    # 3. 最后兜底：最近工作日
    d = today
    while d.weekday() >= 5:  # Sat=5, Sun=6
        d -= timedelta(days=1)
    return d


# ---------------------------------------------------------------------------
# Stock industry classification (cached full-market scan)
# ---------------------------------------------------------------------------

STOCK_INDUSTRY_TABLE = "stock_industry"
STOCK_INDUSTRY_TTL = 30 * 24 * 3600  # 30 天


def get_stock_industry(symbol: str) -> Optional[str]:
    """获取股票行业分类, 30 天 TTL 缓存, 全市场扫描写入。

    Fallback: AkShare stock_zh_a_spot_em 失败 -> None (走 conglomerate 集群)。
    """
    cached = cache.fetch_records(
        table=STOCK_INDUSTRY_TABLE,
        filters={COL_CODE: symbol},
        ttl_seconds=STOCK_INDUSTRY_TTL,
        limit=1,
    )
    if cached:
        industry = cached[0].get(COL_INDUSTRY)
        if industry:
            logger.info("📦 [cache] stock_industry 命中: %s -> %s", symbol, industry)
            return str(industry)

    try:
        df = ak.stock_zh_a_spot_em()
    except Exception as exc:
        logger.error("AkShare stock_zh_a_spot_em error: %s", exc)
        return None

    if df is None or df.empty:
        return None

    code_col = next((c for c in df.columns if "代码" in str(c)), None)
    industry_col = next((c for c in df.columns if "行业" in str(c)), None)
    if code_col is None or industry_col is None:
        logger.warning("stock_zh_a_spot_em columns unexpected: %s", list(df.columns))
        return None

    records: list[dict] = []
    industry_for_symbol: Optional[str] = None
    for _, row in df.iterrows():
        code = str(row.get(code_col, ""))
        ind = str(row.get(industry_col, ""))
        if code and ind:
            records.append({COL_CODE: code, COL_INDUSTRY: ind, COL_NAME: str(row.get("名称", ""))})
            if code == symbol:
                industry_for_symbol = ind

    if records:
        cache.upsert_records(STOCK_INDUSTRY_TABLE, records, key_columns=[COL_CODE])
        logger.info("🆕 [cache] stock_industry 写入 %d 行（全市场）", len(records))

    return industry_for_symbol


# ---------------------------------------------------------------------------
# Historical PB series (for percentile-based valuation)
# ---------------------------------------------------------------------------

HISTORY_PB_TABLE = "history_pb"
HISTORY_PB_TTL = 7 * 24 * 3600  # 7 天


def get_history_pb(symbol: str, years: int = 5) -> list[tuple[str, float]]:
    """获取历史 PB 序列, 7 天 TTL 缓存。

    数据源: ak.stock_zh_valuation_baidu(symbol, indicator="市净率", period="全部")
    Fallback: 失败返回空列表 (下游 _compute_pb_percentile 返回 None, 指标跳过)。
    """
    cached = cache.fetch_records(
        table=HISTORY_PB_TABLE,
        filters={COL_CODE: symbol},
        ttl_seconds=HISTORY_PB_TTL,
        order_by=f'"{COL_DATE}" DESC',
    )
    if cached:
        return [(str(r.get(COL_DATE)), float(r.get("pb", 0))) for r in cached if r.get("pb")]

    try:
        df = ak.stock_zh_valuation_baidu(symbol=symbol, indicator="市净率", period="全部")
    except Exception as exc:
        logger.warning("get_history_pb fetch failed for %s: %s", symbol, exc)
        return []

    if df is None or df.empty:
        return []

    # 预期列: 日期 / 数值
    date_col = next((c for c in df.columns if "日期" in str(c) or "date" in str(c).lower()), None)
    val_col = next((c for c in df.columns if "数值" in str(c) or "value" in str(c).lower() or "市净率" in str(c)), None)
    if date_col is None or val_col is None:
        logger.warning("stock_zh_valuation_baidu columns unexpected: %s", list(df.columns))
        return []

    # 过滤 years 年内数据
    df[date_col] = pd.to_datetime(df[date_col])
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=365 * years)
    df = df[df[date_col] >= cutoff]

    records = [
        {COL_CODE: symbol, COL_DATE: row[date_col].strftime("%Y-%m-%d"), "pb": float(row[val_col])}
        for _, row in df.iterrows() if pd.notna(row[val_col])
    ]
    if records:
        cache.upsert_records(HISTORY_PB_TABLE, records, key_columns=[COL_CODE, COL_DATE])

    return [(r[COL_DATE], r["pb"]) for r in records]


def _compute_pb_percentile(pb_series: list[tuple[str, float]], current_pb: float) -> float | None:
    """计算当前 PB 在历史序列中的分位数 (0.0~1.0)。

    Returns None if series < 2 points or current_pb invalid.
    """
    if not pb_series or len(pb_series) < 2 or current_pb is None or current_pb <= 0:
        return None
    values = [v for _, v in pb_series if v and v > 0]
    if len(values) < 2:
        return None
    values_sorted = sorted(values)
    rank = sum(1 for v in values_sorted if v < current_pb)
    return rank / (len(values_sorted) - 1)
