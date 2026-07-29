"""Resolve industry name / stock ticker to cluster key.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
from __future__ import annotations

from valor.strategy.industry_clusters import INDUSTRY_TO_CLUSTER
from valor.strategy.stock_cluster_map import lookup_stock_cluster


def resolve(industry: str | None) -> str:
    """Map industry name to cluster key; unknown/None -> conglomerate."""
    if not industry:
        return "conglomerate"
    return INDUSTRY_TO_CLUSTER.get(industry.strip(), "conglomerate")


def resolve_stock(symbol: str) -> tuple[str | None, str]:
    """Resolve a stock ticker to (industry_label, cluster_key).

    Priority:
      1. Static STOCK_CLUSTER_MAP (local, O(1), covers ~360 core A-shares)
      2. Remote stock_individual_info_em -> INDUSTRY_TO_CLUSTER (fallback for
         stocks outside the static map)
      3. (None, "conglomerate") as final fallback

    The static map is authoritative for the three telecom carriers
    (601728/600050/600941) which are mapped to utility_transport, not tmt.
    """
    entry = lookup_stock_cluster(symbol)
    if entry:
        return entry

    industry = _fetch_industry_remote(symbol)
    if industry:
        return (industry, resolve(industry))

    return (None, "conglomerate")


def _fetch_industry_remote(symbol: str) -> str | None:
    """Fetch industry name via akshare stock_individual_info_em.

    Returns the industry string on success, None on any failure.
    Kept lazy so the module imports without akshare installed.
    """
    if not symbol:
        return None
    try:
        import akshare as ak  # noqa: PLC0415
        df = ak.stock_individual_info_em(symbol=str(symbol).strip())
    except Exception:
        return None
    if df is None or df.empty:
        return None

    item_col = next((c for c in df.columns if "item" in str(c).lower()), None)
    value_col = next((c for c in df.columns if "value" in str(c).lower()), None)
    if item_col is None or value_col is None:
        return None

    for _, row in df.iterrows():
        label = str(row.get(item_col, ""))
        if "行业" in label:
            val = row.get(value_col)
            if val is not None and str(val).strip():
                return str(val).strip()
    return None
