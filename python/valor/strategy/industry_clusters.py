"""Industry cluster configuration: Pydantic models + 10 cluster constants.

License: Apache-2.0 OR GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class MetricJudge(str, Enum):
    THRESHOLD_GT = "threshold_gt"
    THRESHOLD_LT = "threshold_lt"
    TREND_UP = "trend_up"
    TREND_DOWN = "trend_down"
    RANGE = "range"


class FallbackSource(str, Enum):
    NONE = "none"
    LLM = "llm"
    ONLINE_SEARCH = "online_search"
    COMPUTED = "computed"


class MetricSpec(BaseModel):
    field: str
    label: str
    judge: MetricJudge
    threshold: float | None = None
    threshold_low: float | None = None
    threshold_high: float | None = None
    fallback: FallbackSource = FallbackSource.NONE
    fallback_hint: str = ""
    missing_signal: str = "neutral"
    period: str = "annual"
    dynamic_baseline: str | None = None
    reference_only: bool = False
    description: str = ""


class DimensionSpec(BaseModel):
    name: str
    label: str
    metrics: list[MetricSpec]
    rule: str = "majority"
    weight: float


class IndustryCluster(BaseModel):
    key: str
    label: str
    dimensions: list[DimensionSpec]
    valuation_method: str
    notes: str = ""


def _conglomerate_cluster() -> IndustryCluster:
    """通用兜底集群, 阈值与现有 fundamentals.py 硬编码完全一致."""
    return IndustryCluster(
        key="conglomerate",
        label="综合",
        valuation_method="pe",
        notes="兜底集群, 沿用通用五维度框架, 阈值与改造前 fundamentals.py 一致",
        dimensions=[
            DimensionSpec(
                name="profitability", label="盈利能力", weight=0.20,
                metrics=[
                    MetricSpec(field="return_on_equity", label="ROE",
                               judge=MetricJudge.THRESHOLD_GT, threshold=0.15),
                    MetricSpec(field="net_margin", label="净利率",
                               judge=MetricJudge.THRESHOLD_GT, threshold=0.20),
                    MetricSpec(field="operating_margin", label="营业利润率",
                               judge=MetricJudge.THRESHOLD_GT, threshold=0.15),
                ],
            ),
            DimensionSpec(
                name="growth", label="成长性", weight=0.20,
                metrics=[
                    MetricSpec(field="revenue_growth", label="营收增长率",
                               judge=MetricJudge.THRESHOLD_GT, threshold=0.10),
                    MetricSpec(field="earnings_growth", label="净利润增长率",
                               judge=MetricJudge.THRESHOLD_GT, threshold=0.10),
                    MetricSpec(field="book_value_growth", label="净资产增长率",
                               judge=MetricJudge.THRESHOLD_GT, threshold=0.10),
                ],
            ),
            DimensionSpec(
                name="financial_health", label="财务健康", weight=0.20,
                metrics=[
                    MetricSpec(field="current_ratio", label="流动比率",
                               judge=MetricJudge.THRESHOLD_GT, threshold=1.5),
                    MetricSpec(field="debt_to_equity", label="资产负债率",
                               judge=MetricJudge.THRESHOLD_LT, threshold=0.5),
                    MetricSpec(field="free_cash_flow_per_share", label="FCF/EPS",
                               judge=MetricJudge.THRESHOLD_GT, threshold=0.0),
                ],
            ),
            DimensionSpec(
                name="valuation", label="估值比率", weight=0.20,
                metrics=[
                    MetricSpec(field="pe_ratio", label="市盈率",
                               judge=MetricJudge.THRESHOLD_LT, threshold=25),
                    MetricSpec(field="price_to_book", label="市净率",
                               judge=MetricJudge.THRESHOLD_LT, threshold=3),
                    MetricSpec(field="price_to_sales", label="市销率",
                               judge=MetricJudge.THRESHOLD_LT, threshold=5),
                ],
            ),
            DimensionSpec(
                name="shareholder_return", label="股东回报", weight=0.20,
                metrics=[
                    MetricSpec(field="dividend_yield", label="股息率",
                               judge=MetricJudge.THRESHOLD_GT, threshold=0.04),
                ],
            ),
        ],
    )


# 占位: Task 2 填充其余 9 集群
_CLUSTERS: dict[str, IndustryCluster] = {
    "conglomerate": _conglomerate_cluster(),
}


def _build_industry_to_cluster() -> dict[str, str]:
    """申万一级 31 个行业名 -> 集群 key. Task 2 扩展."""
    return {
        "综合": "conglomerate",
    }


INDUSTRY_TO_CLUSTER: dict[str, str] = _build_industry_to_cluster()

INDUSTRY_CLUSTERS: dict[str, IndustryCluster] = _CLUSTERS