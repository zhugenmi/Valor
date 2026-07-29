"""Unit tests for industry cluster configuration."""
from valor.strategy.industry_clusters import (
    INDUSTRY_CLUSTERS,
    INDUSTRY_TO_CLUSTER,
)


# ---------------------------------------------------------------------------
# Conglomerate (Task 1)
# ---------------------------------------------------------------------------

def test_conglomerate_cluster_exists_and_has_5_dimensions():
    cluster = INDUSTRY_CLUSTERS["conglomerate"]
    assert cluster.key == "conglomerate"
    assert len(cluster.dimensions) == 5
    dim_names = {d.name for d in cluster.dimensions}
    assert dim_names == {
        "profitability", "growth", "financial_health", "valuation", "shareholder_return",
    }


def test_conglomerate_weights_sum_to_one():
    cluster = INDUSTRY_CLUSTERS["conglomerate"]
    total = sum(d.weight for d in cluster.dimensions)
    assert abs(total - 1.0) < 1e-6


def test_conglomerate_thresholds_match_legacy():
    """conglomerate 阈值与现有 fundamentals.py 硬编码一致 (回归锚点)."""
    cluster = INDUSTRY_CLUSTERS["conglomerate"]
    dims = {d.name: d for d in cluster.dimensions}
    # profitability: ROE>0.15, net_margin>0.20, operating_margin>0.15
    prof = {m.field: m for m in dims["profitability"].metrics}
    assert prof["return_on_equity"].threshold == 0.15
    assert prof["net_margin"].threshold == 0.20
    assert prof["operating_margin"].threshold == 0.15
    # growth: revenue_growth>0.10, earnings_growth>0.10, book_value_growth>0.10
    grow = {m.field: m for m in dims["growth"].metrics}
    assert grow["revenue_growth"].threshold == 0.10
    assert grow["earnings_growth"].threshold == 0.10
    assert grow["book_value_growth"].threshold == 0.10
    # valuation: pe<25, pb<3, ps<5
    val = {m.field: m for m in dims["valuation"].metrics}
    assert val["pe_ratio"].threshold == 25
    assert val["price_to_book"].threshold == 3
    assert val["price_to_sales"].threshold == 5


# ---------------------------------------------------------------------------
# Task 2: all 10 clusters present
# ---------------------------------------------------------------------------

def test_all_10_clusters_present():
    expected_keys = {
        "financial", "real_estate", "cyclical_resource", "manufacturing",
        "consumer_staples", "consumer_discretionary", "pharma", "tmt",
        "utility_transport", "conglomerate",
    }
    assert expected_keys.issubset(set(INDUSTRY_CLUSTERS.keys()))


def test_all_clusters_weights_sum_to_one():
    """每集群维度权重和 = 1.0."""
    for key, cluster in INDUSTRY_CLUSTERS.items():
        total = sum(d.weight for d in cluster.dimensions)
        assert abs(total - 1.0) < 1e-6, f"{key} weights sum={total}"


def test_all_10_clusters_dimensions_at_least_2():
    """每集群应至少有 2 个维度."""
    for key, cluster in INDUSTRY_CLUSTERS.items():
        assert len(cluster.dimensions) >= 2, f"{key} has {len(cluster.dimensions)} dims"


# ---------------------------------------------------------------------------
# Per-cluster config tests
# ---------------------------------------------------------------------------

def test_financial_cluster_config():
    cluster = INDUSTRY_CLUSTERS["financial"]
    assert cluster.valuation_method == "pb"
    dims = {d.name: d for d in cluster.dimensions}
    assert dims["financial_health"].weight == 0.35
    # 银行专项指标存在
    health_metrics = {m.field for m in dims["financial_health"].metrics}
    assert "non_performing_loan_ratio" in health_metrics
    assert "provision_coverage" in health_metrics
    assert "core_tier1_capital_ratio" in health_metrics
    # NIM 在 profitability
    prof_metrics = {m.field for m in dims["profitability"].metrics}
    assert "net_interest_margin" in prof_metrics
    # NIM uses dynamic_baseline
    nim = next(m for m in dims["profitability"].metrics if m.field == "net_interest_margin")
    assert nim.dynamic_baseline == "industry_avg_nim"


def test_tmt_cluster_has_no_shareholder_return():
    """TMT 移除 shareholder_return 维度."""
    cluster = INDUSTRY_CLUSTERS["tmt"]
    dim_names = {d.name for d in cluster.dimensions}
    assert "shareholder_return" not in dim_names
    assert "growth" in dim_names
    grow = {d.name: d for d in cluster.dimensions if d.name == "growth"}["growth"]
    assert grow.weight == 0.45
    grow_metrics = {m.field for m in grow.metrics}
    assert "earnings_growth" in grow_metrics  # PEG 计算需要


def test_utility_transport_has_no_growth():
    """公用事业移除 growth 维度."""
    cluster = INDUSTRY_CLUSTERS["utility_transport"]
    dim_names = {d.name for d in cluster.dimensions}
    assert "growth" not in dim_names


def test_cyclical_resource_pe_is_reference_only():
    """周期资源 PE 降为参考项不计入投票."""
    cluster = INDUSTRY_CLUSTERS["cyclical_resource"]
    val = {d.name: d for d in cluster.dimensions if d.name == "valuation"}["valuation"]
    pe = next(m for m in val.metrics if m.field == "pe_ratio")
    assert pe.reference_only is True
    pb_pct = next(m for m in val.metrics if m.field == "pb_percentile_5y")
    assert pb_pct.reference_only is False


# ---------------------------------------------------------------------------
# Remaining cluster configs (spec §5.2-5.7)
# ---------------------------------------------------------------------------

def test_real_estate_cluster_config():
    cluster = INDUSTRY_CLUSTERS["real_estate"]
    assert cluster.valuation_method == "pb"
    dims = {d.name: d for d in cluster.dimensions}
    assert dims["financial_health"].weight == 0.40
    health_metrics = {m.field for m in dims["financial_health"].metrics}
    assert "adj_debt_to_asset" in health_metrics
    assert "net_debt_to_equity" in health_metrics
    assert "cash_to_short_debt" in health_metrics
    assert "inventory_turnover" in health_metrics
    assert "gross_margin" in health_metrics


def test_manufacturing_cluster_config():
    cluster = INDUSTRY_CLUSTERS["manufacturing"]
    assert cluster.valuation_method == "pe"
    dims = {d.name: d for d in cluster.dimensions}
    assert dims["financial_health"].weight == 0.30
    health_metrics = {m.field for m in dims["financial_health"].metrics}
    assert "asset_turnover" in health_metrics
    assert "receivable_to_revenue" in health_metrics
    grow_metrics = {m.field for m in dims["growth"].metrics}
    assert "capex_to_depreciation" in grow_metrics


def test_consumer_staples_cluster_config():
    cluster = INDUSTRY_CLUSTERS["consumer_staples"]
    assert cluster.valuation_method == "pe"
    dims = {d.name: d for d in cluster.dimensions}
    assert dims["profitability"].weight == 0.30
    prof_metrics = {m.field for m in dims["profitability"].metrics}
    assert "gross_margin" in prof_metrics
    grow_metrics = {m.field for m in dims["growth"].metrics}
    assert "contract_liability" in grow_metrics
    val_metrics = {m.field for m in dims["valuation"].metrics}
    assert "price_to_sales" in val_metrics


def test_consumer_discretionary_cluster_config():
    cluster = INDUSTRY_CLUSTERS["consumer_discretionary"]
    assert cluster.valuation_method == "pe"
    dims = {d.name: d for d in cluster.dimensions}
    health_metrics = {m.field for m in dims["financial_health"].metrics}
    assert "inventory_turnover" in health_metrics
    assert "sales_expense_ratio" in health_metrics
    assert "ocf_to_net_profit" in health_metrics


def test_pharma_cluster_config():
    cluster = INDUSTRY_CLUSTERS["pharma"]
    assert cluster.valuation_method == "peg"
    dims = {d.name: d for d in cluster.dimensions}
    grow_metrics = {m.field for m in dims["growth"].metrics}
    assert "r_and_d_to_revenue" in grow_metrics
    # earnings_growth 在 growth 维度中用于 PEG 计算
    assert "earnings_growth" in grow_metrics
    health_metrics = {m.field for m in dims["financial_health"].metrics}
    assert "r_and_d_capitalization_rate" in health_metrics


# ---------------------------------------------------------------------------
# INDUSTRY_TO_CLUSTER mapping (31 申万一级)
# ---------------------------------------------------------------------------

def test_industry_to_cluster_covers_31_sw_industries():
    """INDUSTRY_TO_CLUSTER 覆盖全部 31 个申万一级行业名."""
    expected_industries = {
        "银行", "非银金融",
        "房地产", "建筑装饰", "建筑材料",
        "煤炭", "石油石化", "有色金属", "钢铁", "基础化工",
        "电力设备", "机械设备", "国防军工", "汽车",
        "食品饮料", "农林牧渔", "纺织服饰", "轻工制造",
        "家用电器", "商贸零售", "社会服务", "美容护理",
        "医药生物",
        "电子", "计算机", "通信", "传媒",
        "公用事业", "交通运输", "环保",
        "综合",
    }
    assert len(expected_industries) == 31
    for industry in expected_industries:
        assert industry in INDUSTRY_TO_CLUSTER, f"Missing industry: {industry}"


def test_industry_to_cluster_correct_mapping():
    """抽查关键映射."""
    assert INDUSTRY_TO_CLUSTER["银行"] == "financial"
    assert INDUSTRY_TO_CLUSTER["非银金融"] == "financial"
    assert INDUSTRY_TO_CLUSTER["房地产"] == "real_estate"
    assert INDUSTRY_TO_CLUSTER["煤炭"] == "cyclical_resource"
    assert INDUSTRY_TO_CLUSTER["电力设备"] == "manufacturing"
    assert INDUSTRY_TO_CLUSTER["食品饮料"] == "consumer_staples"
    assert INDUSTRY_TO_CLUSTER["家用电器"] == "consumer_discretionary"
    assert INDUSTRY_TO_CLUSTER["医药生物"] == "pharma"
    assert INDUSTRY_TO_CLUSTER["电子"] == "tmt"
    assert INDUSTRY_TO_CLUSTER["公用事业"] == "utility_transport"
    assert INDUSTRY_TO_CLUSTER["综合"] == "conglomerate"