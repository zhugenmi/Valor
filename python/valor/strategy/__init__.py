"""Industry-customized fundamental analysis strategy module.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from valor.strategy.industry_clusters import (
    INDUSTRY_CLUSTERS,
    INDUSTRY_TO_CLUSTER,
    DimensionSpec,
    FallbackSource,
    IndustryCluster,
    MetricJudge,
    MetricSpec,
)
from valor.strategy.cluster_resolver import resolve, resolve_stock
from valor.strategy.metric_evaluators import evaluate_dimension, evaluate_metric

__all__ = [
    "INDUSTRY_CLUSTERS",
    "INDUSTRY_TO_CLUSTER",
    "IndustryCluster",
    "DimensionSpec",
    "MetricSpec",
    "MetricJudge",
    "FallbackSource",
    "resolve",
    "resolve_stock",
    "evaluate_dimension",
    "evaluate_metric",
]