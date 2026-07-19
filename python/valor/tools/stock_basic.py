"""Stock basic info - get stock name from code, with SQLite TTL cache.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from __future__ import annotations

from typing import Optional

import akshare as ak
import pandas as pd
from loguru import logger

from valor.adapters.data.akshare_cache import COL_CODE, COL_NAME, cache
from valor.utils.logging_config import setup_logger

_logger = setup_logger("stock_basic")

STOCK_BASIC_TABLE = "stock_basic"
STOCK_BASIC_TTL = 30 * 24 * 3600  # 30 天


def get_stock_name(symbol: str) -> Optional[str]:
    """获取股票名称，30 天 TTL 缓存。

    缓存命中：直接返回 名称 字段。
    缓存未命中：调 ak.stock_zh_a_spot_em() 全市场扫描，写入缓存后返回。
    远程失败：返回 None（与原行为一致）。
    """
    cached = cache.fetch_records(
        table=STOCK_BASIC_TABLE,
        filters={COL_CODE: symbol},
        ttl_seconds=STOCK_BASIC_TTL,
        limit=1,
    )
    if cached:
        name = cached[0].get(COL_NAME)
        if name:
            _logger.info("📦 [cache] stock_basic 命中: %s -> %s", symbol, name)
            return str(name)

    try:
        df = ak.stock_zh_a_spot_em()
    except Exception as exc:
        _logger.error("AkShare stock_zh_a_spot_em error: %s", exc)
        return None

    if df is None or df.empty:
        return None

    # 动态识别列名（与原逻辑一致，兼容列名微小差异）
    code_col = next((c for c in df.columns if "代码" in str(c)), None)
    name_col = next((c for c in df.columns if "名称" in str(c)), None)
    if code_col is None or name_col is None:
        logger.warning("stock_zh_a_spot_em columns unexpected: %s", list(df.columns))
        return None

    # 一次性把全市场写入缓存（下次任意股票查询都受益）
    records: list[dict] = []
    name_for_symbol: Optional[str] = None
    for _, row in df.iterrows():
        code = str(row.get(code_col, ""))
        name = str(row.get(name_col, ""))
        if code and name:
            records.append({COL_CODE: code, COL_NAME: name})
            if code == symbol:
                name_for_symbol = name

    if records:
        cache.upsert_records(
            STOCK_BASIC_TABLE,
            records,
            key_columns=[COL_CODE],
        )
        _logger.info("🆕 [cache] stock_basic 写入 %d 行（全市场）", len(records))

    return name_for_symbol