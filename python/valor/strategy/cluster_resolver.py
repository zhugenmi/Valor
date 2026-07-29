"""Resolve industry name to cluster key.

License: Apache-2.0 OR GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
from valor.strategy.industry_clusters import INDUSTRY_TO_CLUSTER


def resolve(industry: str | None) -> str:
    """Map industry name to cluster key; unknown/None -> conglomerate."""
    if not industry:
        return "conglomerate"
    return INDUSTRY_TO_CLUSTER.get(industry.strip(), "conglomerate")