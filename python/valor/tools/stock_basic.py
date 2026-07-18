"""Stock basic info - get stock name from code.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from loguru import logger


def get_stock_name(symbol: str) -> str | None:
    """Get Chinese stock name from ticker symbol using AkShare.

    Args:
        symbol: A-share ticker, e.g. "600519"

    Returns:
        Company name string, or symbol itself if lookup fails.
    """
    try:
        import akshare as ak

        df = ak.stock_zh_a_spot_em()
        code_col = next(c for c in df.columns if "代码" in c)
        name_col = next(c for c in df.columns if "名称" in c)
        row = df[df[code_col] == symbol]
        if not row.empty:
            return str(row.iloc[0][name_col])
    except Exception as e:
        logger.warning("Failed to get stock name for {s}: {err}", s=symbol, err=e)
    return None
