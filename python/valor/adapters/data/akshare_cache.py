"""Cached market data helpers backed by SQLite."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import os
from typing import Dict, List, Optional
from typing import Sequence, Tuple

import akshare as ak
import pandas as pd

from valor.adapters.data.sqlite_cache import AkshareSQLiteCache
from valor.network.proxy_manager import ProxyManager
from valor.adapters.data.baostock_client import query_history_k_data_plus, query_trade_dates
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

BASE_DIR = Path(__file__).resolve().parents[2]
_default_cache_path = BASE_DIR / "data" / "market_data_cache.db"
CACHE_PATH = Path(os.getenv("MARKET_CACHE_DB_PATH", str(_default_cache_path)))
HISTORY_TABLE = "baostock_history_k"
STOCK_NEWS_EM_TABLE = "stock_news_em_daily"
SPOT_TABLE = "stock_bid_ask_em"

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


def get_stock_spot_row(symbol: str, ttl_seconds: int = 600) -> Optional[pd.Series]:
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

    df = _call_with_retry(
        lambda: ak.stock_bid_ask_em(symbol=symbol),
        SPOT_TABLE,
    )
    if df is None or df.empty:
        return None

    row_dict = {COL_CODE: symbol}
    for _, r in df.iterrows():
        item = str(r["item"])
        if item in _BID_ASK_FIELD_MAP:
            row_dict[_BID_ASK_FIELD_MAP[item]] = r["value"]

    if "最新价" not in row_dict:
        return None

    cache.upsert_records(
        SPOT_TABLE,
        [row_dict],
        key_columns=[COL_CODE],
    )
    _log_cache_upsert(SPOT_TABLE, symbol, 1)
    return pd.Series(row_dict)


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
        if cached:
            logger.warning(
                "⚠️ 远程拉取财报报表失败，降级返回缓存: %s %s (缓存行数=%d)",
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


def _expected_trading_days(start_date: datetime, end_date: datetime) -> Sequence[pd.Timestamp]:
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    df = query_trade_dates(start_date, end_date)
    if df.empty:
        return pd.bdate_range(start=start_date, end=end_date)
    df["calendar_date"] = pd.to_datetime(df["calendar_date"])
    trading = df[df["is_trading_day"].astype(int) == 1]["calendar_date"].dt.normalize()
    return trading.tolist()


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
        raw = query_history_k_data_plus(
            symbol=symbol,
            start_date=seg_start.strftime("%Y-%m-%d"),
            end_date=seg_end.strftime("%Y-%m-%d"),
            adjust=adjust,
        )
        prepared = _prepare_history_frame(raw, symbol, adjust)
        if not prepared.empty:
            _cache_history_rows(prepared)
            new_frames.append(prepared)

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
