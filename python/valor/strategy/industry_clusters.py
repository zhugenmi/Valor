"""Industry cluster configuration: Pydantic models + 10 cluster constants.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
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
    baseline_multiplier: float = 1.0
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


# ---------------------------------------------------------------------------
# Cluster factory functions
# ---------------------------------------------------------------------------

def _financial_cluster() -> IndustryCluster:
    return IndustryCluster(
        key="financial", label="金融", valuation_method="pb",
        notes="银行经营风险而非产品, PE和成长性意义有限, 重点看资产质量。"
              "净息差1.4%为2024年商业银行均值, 与行业均值比较更准确(支持dynamic_baseline)。",
        dimensions=[
            DimensionSpec(name="profitability", label="盈利能力", weight=0.10, metrics=[
                MetricSpec(field="return_on_equity", label="ROE",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.10),
                MetricSpec(field="net_interest_margin", label="净息差",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.014,
                           fallback=FallbackSource.ONLINE_SEARCH,
                           fallback_hint="商业银行净息差约1.4%",
                           dynamic_baseline="industry_avg_nim"),
            ]),
            DimensionSpec(name="growth", label="成长性", weight=0.10, metrics=[
                MetricSpec(field="revenue_growth", label="营收增长率",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.05),
            ]),
            DimensionSpec(name="financial_health", label="财务健康", weight=0.35, metrics=[
                MetricSpec(field="non_performing_loan_ratio", label="不良贷款率",
                           judge=MetricJudge.THRESHOLD_LT, threshold=0.015,
                           fallback=FallbackSource.ONLINE_SEARCH,
                           dynamic_baseline="industry_avg_npl"),
                MetricSpec(field="provision_coverage", label="拨备覆盖率",
                           judge=MetricJudge.THRESHOLD_GT, threshold=2.0,
                           fallback=FallbackSource.ONLINE_SEARCH),
                MetricSpec(field="core_tier1_capital_ratio", label="核心一级资本充足率",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.085,
                           fallback=FallbackSource.LLM,
                           fallback_hint="巴塞尔III监管底线8.5%"),
            ]),
            DimensionSpec(name="valuation", label="估值", weight=0.25, metrics=[
                MetricSpec(field="price_to_book", label="市净率",
                           judge=MetricJudge.THRESHOLD_LT, threshold=1.0),
            ]),
            DimensionSpec(name="shareholder_return", label="股东回报", weight=0.20, metrics=[
                MetricSpec(field="dividend_yield", label="股息率",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.03),
            ]),
        ],
    )


def _real_estate_cluster() -> IndustryCluster:
    return IndustryCluster(
        key="real_estate", label="地产与建筑", valuation_method="pb",
        notes="高杠杆预售制长周期, 核心看资金链安全和去化速度(三道红线)。"
              "存货周转率提升需结合毛利率判断--若周转率上升但毛利率下降, "
              "可能是降价促销去化, 未必是好事; 两者同向上行才是健康去化。"
              "因此 gross_margin 作为 financial_health 维度的辅助指标共同投票。",
        dimensions=[
            DimensionSpec(name="profitability", label="盈利能力", weight=0.15, metrics=[
                MetricSpec(field="return_on_equity", label="ROE",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.12),
                MetricSpec(field="net_margin", label="净利率",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.08),
            ]),
            DimensionSpec(name="growth", label="成长性", weight=0.10, metrics=[
                MetricSpec(field="earnings_growth", label="净利润增长率",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.05),
            ]),
            DimensionSpec(name="financial_health", label="财务健康", weight=0.40, metrics=[
                MetricSpec(field="adj_debt_to_asset", label="调整后资产负债率",
                           judge=MetricJudge.THRESHOLD_LT, threshold=0.70,
                           fallback=FallbackSource.COMPUTED),
                MetricSpec(field="net_debt_to_equity", label="净负债率",
                           judge=MetricJudge.THRESHOLD_LT, threshold=1.0,
                           fallback=FallbackSource.COMPUTED),
                MetricSpec(field="cash_to_short_debt", label="现金短债比",
                           judge=MetricJudge.THRESHOLD_GT, threshold=1.0,
                           fallback=FallbackSource.COMPUTED),
                MetricSpec(field="inventory_turnover", label="存货周转率",
                           judge=MetricJudge.TREND_UP,
                           fallback=FallbackSource.COMPUTED),
                MetricSpec(field="gross_margin", label="毛利率",
                           judge=MetricJudge.TREND_UP,
                           fallback=FallbackSource.COMPUTED),
            ]),
            DimensionSpec(name="valuation", label="估值", weight=0.20, metrics=[
                MetricSpec(field="price_to_book", label="市净率",
                           judge=MetricJudge.THRESHOLD_LT, threshold=2.0),
            ]),
            DimensionSpec(name="shareholder_return", label="股东回报", weight=0.15, metrics=[
                MetricSpec(field="dividend_yield", label="股息率",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.02),
            ]),
        ],
    )


def _cyclical_resource_cluster() -> IndustryCluster:
    return IndustryCluster(
        key="cyclical_resource", label="周期资源", valuation_method="pb_percentile",
        notes="产品同质化, 盈利由大宗价格驱动, 周期顶底判断比绝对数值重要。"
              "PE 作为参考项不计入投票--周期顶部利润高 PE 反而低, "
              "PE<15 可能是周期顶部信号而非低估, 主信号以 PB 历史分位为准。"
              "当 pb_percentile_5y 缺失时, valuation 维度按剩余投票指标(无)判 neutral。",
        dimensions=[
            DimensionSpec(name="profitability", label="盈利能力", weight=0.10, metrics=[
                MetricSpec(field="net_margin", label="净利率",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.05),
            ]),
            DimensionSpec(name="growth", label="成长性", weight=0.05, metrics=[
                MetricSpec(field="revenue_growth", label="营收增长率",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.05),
            ]),
            DimensionSpec(name="financial_health", label="财务健康", weight=0.20, metrics=[
                MetricSpec(field="current_ratio", label="流动比率",
                           judge=MetricJudge.THRESHOLD_GT, threshold=1.0),
                MetricSpec(field="debt_to_equity", label="资产负债率",
                           judge=MetricJudge.THRESHOLD_LT, threshold=0.6),
            ]),
            DimensionSpec(name="valuation", label="估值", weight=0.35, metrics=[
                MetricSpec(field="pb_percentile_5y", label="5年PB分位",
                           judge=MetricJudge.THRESHOLD_LT, threshold=0.30,
                           fallback=FallbackSource.ONLINE_SEARCH),
                MetricSpec(field="pe_ratio", label="市盈率",
                           judge=MetricJudge.THRESHOLD_LT, threshold=15,
                           reference_only=True),
            ]),
            DimensionSpec(name="shareholder_return", label="股东回报", weight=0.30, metrics=[
                MetricSpec(field="dividend_yield", label="股息率",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.04),
            ]),
        ],
    )


def _manufacturing_cluster() -> IndustryCluster:
    return IndustryCluster(
        key="manufacturing", label="制造与设备", valuation_method="pe",
        notes="重资产规模效应, 资本开支周期决定盈利波动",
        dimensions=[
            DimensionSpec(name="profitability", label="盈利能力", weight=0.20, metrics=[
                MetricSpec(field="return_on_equity", label="ROE",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.12),
                MetricSpec(field="operating_margin", label="营业利润率",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.10),
            ]),
            DimensionSpec(name="growth", label="成长性", weight=0.20, metrics=[
                MetricSpec(field="revenue_growth", label="营收增长率",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.10),
                MetricSpec(field="capex_to_depreciation", label="资本开支/折旧",
                           judge=MetricJudge.THRESHOLD_GT, threshold=1.5,
                           fallback=FallbackSource.COMPUTED),
            ]),
            DimensionSpec(name="financial_health", label="财务健康", weight=0.30, metrics=[
                MetricSpec(field="asset_turnover", label="资产周转率",
                           judge=MetricJudge.TREND_UP,
                           fallback=FallbackSource.COMPUTED),
                MetricSpec(field="receivable_to_revenue", label="应收/营收",
                           judge=MetricJudge.TREND_DOWN,
                           fallback=FallbackSource.COMPUTED),
                MetricSpec(field="current_ratio", label="流动比率",
                           judge=MetricJudge.THRESHOLD_GT, threshold=1.5),
            ]),
            DimensionSpec(name="valuation", label="估值", weight=0.15, metrics=[
                MetricSpec(field="pe_ratio", label="市盈率",
                           judge=MetricJudge.THRESHOLD_LT, threshold=20),
            ]),
            DimensionSpec(name="shareholder_return", label="股东回报", weight=0.15, metrics=[
                MetricSpec(field="dividend_yield", label="股息率",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.02),
            ]),
        ],
    )


def _consumer_staples_cluster() -> IndustryCluster:
    return IndustryCluster(
        key="consumer_staples", label="消费必选", valuation_method="pe",
        notes="品牌护城河渠道壁垒, 核心看品牌溢价能力和渠道健康度",
        dimensions=[
            DimensionSpec(name="profitability", label="盈利能力", weight=0.30, metrics=[
                MetricSpec(field="gross_margin", label="毛利率",
                           judge=MetricJudge.TREND_UP),
                MetricSpec(field="net_margin", label="净利率",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.10),
                MetricSpec(field="return_on_equity", label="ROE",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.15),
            ]),
            DimensionSpec(name="growth", label="成长性", weight=0.20, metrics=[
                MetricSpec(field="revenue_growth", label="营收增长率",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.08),
                MetricSpec(field="contract_liability", label="合同负债",
                           judge=MetricJudge.TREND_UP,
                           fallback=FallbackSource.COMPUTED),
            ]),
            DimensionSpec(name="financial_health", label="财务健康", weight=0.15, metrics=[
                MetricSpec(field="inventory_turnover", label="存货周转率",
                           judge=MetricJudge.TREND_UP,
                           fallback=FallbackSource.COMPUTED),
                MetricSpec(field="current_ratio", label="流动比率",
                           judge=MetricJudge.THRESHOLD_GT, threshold=1.5),
            ]),
            DimensionSpec(name="valuation", label="估值", weight=0.20, metrics=[
                MetricSpec(field="price_to_sales", label="市销率",
                           judge=MetricJudge.THRESHOLD_LT, threshold=5),
            ]),
            DimensionSpec(name="shareholder_return", label="股东回报", weight=0.15, metrics=[
                MetricSpec(field="dividend_yield", label="股息率",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.02),
            ]),
        ],
    )


def _consumer_discretionary_cluster() -> IndustryCluster:
    return IndustryCluster(
        key="consumer_discretionary", label="消费可选", valuation_method="pe",
        notes="受经济周期影响大, 关注用户粘性和复购率, 警惕烧钱换增长",
        dimensions=[
            DimensionSpec(name="profitability", label="盈利能力", weight=0.25, metrics=[
                MetricSpec(field="return_on_equity", label="ROE",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.12),
                MetricSpec(field="net_margin", label="净利率",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.08),
            ]),
            DimensionSpec(name="growth", label="成长性", weight=0.20, metrics=[
                MetricSpec(field="revenue_growth", label="营收增长率",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.10),
            ]),
            DimensionSpec(name="financial_health", label="财务健康", weight=0.20, metrics=[
                MetricSpec(field="inventory_turnover", label="存货周转率",
                           judge=MetricJudge.TREND_UP,
                           fallback=FallbackSource.COMPUTED),
                MetricSpec(field="sales_expense_ratio", label="销售费用率",
                           judge=MetricJudge.TREND_DOWN,
                           fallback=FallbackSource.COMPUTED),
                MetricSpec(field="ocf_to_net_profit", label="经营现金流/净利润",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.8,
                           fallback=FallbackSource.COMPUTED),
            ]),
            DimensionSpec(name="valuation", label="估值", weight=0.20, metrics=[
                MetricSpec(field="pe_ratio", label="市盈率",
                           judge=MetricJudge.THRESHOLD_LT, threshold=25),
            ]),
            DimensionSpec(name="shareholder_return", label="股东回报", weight=0.15, metrics=[
                MetricSpec(field="dividend_yield", label="股息率",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.02),
            ]),
        ],
    )


def _pharma_cluster() -> IndustryCluster:
    return IndustryCluster(
        key="pharma", label="医药", valuation_method="peg",
        notes="研发驱动政策敏感长周期, 创新药和仿制药/中药逻辑不同。"
              "growth 维度含 earnings_growth 用于 PEG 估值计算。",
        dimensions=[
            DimensionSpec(name="profitability", label="盈利能力", weight=0.30, metrics=[
                MetricSpec(field="gross_margin", label="毛利率",
                           judge=MetricJudge.TREND_UP),
                MetricSpec(field="net_margin", label="净利率",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.10),
            ]),
            DimensionSpec(name="growth", label="成长性", weight=0.20, metrics=[
                MetricSpec(field="revenue_growth", label="营收增长率",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.10),
                MetricSpec(field="earnings_growth", label="净利润增长率",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.10),
                MetricSpec(field="r_and_d_to_revenue", label="研发投入占比",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.08,
                           fallback=FallbackSource.LLM),
            ]),
            DimensionSpec(name="financial_health", label="财务健康", weight=0.20, metrics=[
                MetricSpec(field="r_and_d_capitalization_rate", label="研发资本化率",
                           judge=MetricJudge.THRESHOLD_LT, threshold=0.3,
                           fallback=FallbackSource.LLM),
                MetricSpec(field="receivable_to_revenue", label="应收/营收",
                           judge=MetricJudge.TREND_DOWN,
                           fallback=FallbackSource.COMPUTED),
            ]),
            DimensionSpec(name="valuation", label="估值", weight=0.15, metrics=[
                MetricSpec(field="pe_ratio", label="市盈率",
                           judge=MetricJudge.THRESHOLD_LT, threshold=30),
            ]),
            DimensionSpec(name="shareholder_return", label="股东回报", weight=0.15, metrics=[
                MetricSpec(field="dividend_yield", label="股息率",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.01),
            ]),
        ],
    )


def _tmt_cluster() -> IndustryCluster:
    return IndustryCluster(
        key="tmt", label="TMT与科技", valuation_method="peg",
        notes="技术迭代快轻资产研发驱动, 成长性是核心。shareholder_return完全移除-"
              "成长型科技不分红是常态。PEG=pe_ratio/(earnings_growth*100), PEG<1看多。",
        dimensions=[
            DimensionSpec(name="profitability", label="盈利能力", weight=0.15, metrics=[
                MetricSpec(field="gross_margin", label="毛利率",
                           judge=MetricJudge.TREND_UP),
                MetricSpec(field="net_margin", label="净利率",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.10),
            ]),
            DimensionSpec(name="growth", label="成长性", weight=0.45, metrics=[
                MetricSpec(field="revenue_growth", label="营收增长率",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.15),
                MetricSpec(field="earnings_growth", label="净利润增长率",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.15),
                MetricSpec(field="r_and_d_to_revenue", label="研发投入占比",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.10,
                           fallback=FallbackSource.LLM,
                           fallback_hint="科技企业研发投入通常>10%"),
            ]),
            DimensionSpec(name="financial_health", label="财务健康", weight=0.15, metrics=[
                MetricSpec(field="ocf_to_net_profit", label="经营现金流/净利润",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.8,
                           fallback=FallbackSource.COMPUTED),
                MetricSpec(field="current_ratio", label="流动比率",
                           judge=MetricJudge.THRESHOLD_GT, threshold=1.5),
            ]),
            DimensionSpec(name="valuation", label="估值", weight=0.25, metrics=[
                MetricSpec(field="pe_ratio", label="市盈率",
                           judge=MetricJudge.THRESHOLD_LT, threshold=30),
            ]),
        ],
    )


def _utility_transport_cluster() -> IndustryCluster:
    return IndustryCluster(
        key="utility_transport", label="公用事业与交运", valuation_method="dividend_yield",
        notes="类债券属性, 现金流稳定增长缓慢, 核心看股息稳定性和资本开支效率。"
              "growth 维度完全移除--低增长是公用事业常态, 不应因此扣分"
              "(符合‘扣分只发生在核心竞争力维度恶化时’原则)。",
        dimensions=[
            DimensionSpec(name="profitability", label="盈利能力", weight=0.10, metrics=[
                MetricSpec(field="net_margin", label="净利率",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.10),
                MetricSpec(field="return_on_equity", label="ROE",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.08),
            ]),
            DimensionSpec(name="financial_health", label="财务健康", weight=0.20, metrics=[
                MetricSpec(field="free_cash_flow", label="自由现金流",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0,
                           fallback=FallbackSource.COMPUTED),
                MetricSpec(field="capex_to_ocf", label="资本开支/经营现金流",
                           judge=MetricJudge.THRESHOLD_LT, threshold=0.6,
                           fallback=FallbackSource.COMPUTED),
                MetricSpec(field="debt_to_equity", label="资产负债率",
                           judge=MetricJudge.THRESHOLD_LT, threshold=0.6),
            ]),
            DimensionSpec(name="valuation", label="估值", weight=0.30, metrics=[
                MetricSpec(field="price_to_book", label="市净率",
                           judge=MetricJudge.THRESHOLD_LT, threshold=2.0),
            ]),
            DimensionSpec(name="shareholder_return", label="股东回报", weight=0.40, metrics=[
                MetricSpec(field="dividend_yield", label="股息率",
                           judge=MetricJudge.THRESHOLD_GT, threshold=0.04),
                MetricSpec(field="dividend_years", label="连续分红年数",
                           judge=MetricJudge.THRESHOLD_GT, threshold=5,
                           fallback=FallbackSource.COMPUTED),
            ]),
        ],
    )


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
                               judge=MetricJudge.THRESHOLD_GT, threshold=0.0,
                               dynamic_baseline="earnings_per_share",
                               baseline_multiplier=0.8),
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
                               judge=MetricJudge.THRESHOLD_GT, threshold=0.0399),
                ],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Cluster registry
# ---------------------------------------------------------------------------

_CLUSTERS: dict[str, IndustryCluster] = {
    "financial": _financial_cluster(),
    "real_estate": _real_estate_cluster(),
    "cyclical_resource": _cyclical_resource_cluster(),
    "manufacturing": _manufacturing_cluster(),
    "consumer_staples": _consumer_staples_cluster(),
    "consumer_discretionary": _consumer_discretionary_cluster(),
    "pharma": _pharma_cluster(),
    "tmt": _tmt_cluster(),
    "utility_transport": _utility_transport_cluster(),
    "conglomerate": _conglomerate_cluster(),
}


def _build_industry_to_cluster() -> dict[str, str]:
    """申万一级 31 个行业名 -> 集群 key."""
    return {
        "银行": "financial", "非银金融": "financial",
        "房地产": "real_estate", "建筑装饰": "real_estate", "建筑材料": "real_estate",
        "煤炭": "cyclical_resource", "石油石化": "cyclical_resource",
        "有色金属": "cyclical_resource", "钢铁": "cyclical_resource",
        "基础化工": "cyclical_resource",
        "电力设备": "manufacturing", "机械设备": "manufacturing",
        "国防军工": "manufacturing", "汽车": "manufacturing",
        "食品饮料": "consumer_staples", "农林牧渔": "consumer_staples",
        "纺织服饰": "consumer_staples", "轻工制造": "consumer_staples",
        "家用电器": "consumer_discretionary", "商贸零售": "consumer_discretionary",
        "社会服务": "consumer_discretionary", "美容护理": "consumer_discretionary",
        "医药生物": "pharma",
        "电子": "tmt", "计算机": "tmt", "通信": "tmt", "传媒": "tmt",
        "公用事业": "utility_transport", "交通运输": "utility_transport",
        "环保": "utility_transport",
        "综合": "conglomerate",
    }


INDUSTRY_TO_CLUSTER: dict[str, str] = _build_industry_to_cluster()

INDUSTRY_CLUSTERS: dict[str, IndustryCluster] = _CLUSTERS