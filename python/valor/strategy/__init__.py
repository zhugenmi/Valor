"""Industry-customized fundamental analysis strategy module."""

from valor.strategy.industry_clusters import (
    INDUSTRY_CLUSTERS,
    INDUSTRY_TO_CLUSTER,
    DimensionSpec,
    FallbackSource,
    IndustryCluster,
    MetricJudge,
    MetricSpec,
)
from valor.strategy.cluster_resolver import resolve

__all__ = [
    "INDUSTRY_CLUSTERS",
    "INDUSTRY_TO_CLUSTER",
    "IndustryCluster",
    "DimensionSpec",
    "MetricSpec",
    "MetricJudge",
    "FallbackSource",
    "resolve",
]