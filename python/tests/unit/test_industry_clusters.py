"""Unit tests for industry cluster configuration, stock cluster map, and resolver.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
import pytest

from valor.strategy.cluster_resolver import resolve, resolve_stock
from valor.strategy.industry_clusters import (
    INDUSTRY_CLUSTERS,
    INDUSTRY_TO_CLUSTER,
)
from valor.strategy.stock_cluster_map import STOCK_CLUSTER_MAP, lookup_stock_cluster


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


# ---------------------------------------------------------------------------
# stock_cluster_map static mapping
# ---------------------------------------------------------------------------

def test_three_telecom_carriers_mapped_to_utility_transport():
    """三大运营商必须归公用事业，不归 TMT。

    业务定性：类债券+高股息+现金流稳定，而非高成长科技股。
    """
    for code, name in [("601728", "中国电信"), ("600050", "中国联通"), ("600941", "中国移动")]:
        result = lookup_stock_cluster(code)
        assert result is not None
        label, cluster = result
        assert cluster == "utility_transport", f"{name} {code} -> {cluster}"
        assert label == "通信运营"


def test_lookup_returns_none_for_unknown_symbol():
    assert lookup_stock_cluster("999999") is None


def test_lookup_returns_none_for_empty():
    assert lookup_stock_cluster("") is None


def test_lookup_strips_whitespace():
    result = lookup_stock_cluster("  601728  ")
    assert result is not None
    assert result[1] == "utility_transport"


def test_map_covers_at_least_300_stocks():
    """静态表应覆盖沪深300+主要成分股，至少 300 条。"""
    assert len(STOCK_CLUSTER_MAP) >= 300


def test_map_covers_all_10_clusters():
    """10 个集群都应有至少 1 个代表。"""
    clusters = {c for _, c in STOCK_CLUSTER_MAP.values()}
    expected = {
        "financial", "real_estate", "cyclical_resource", "manufacturing",
        "consumer_staples", "consumer_discretionary", "pharma", "tmt",
        "utility_transport", "conglomerate",
    }
    assert clusters == expected


def test_bank_stocks_map_to_financial():
    """招商银行 600036 -> financial."""
    result = lookup_stock_cluster("600036")
    assert result is not None
    assert result[1] == "financial"


def test_maotai_maps_to_consumer_staples():
    """贵州茅台 600519 -> consumer_staples."""
    result = lookup_stock_cluster("600519")
    assert result is not None
    assert result[1] == "consumer_staples"


def test_haier_maps_to_consumer_discretionary():
    """海尔智家 600690 归消费可选/家电，不归制造（去重决策）."""
    result = lookup_stock_cluster("600690")
    assert result is not None
    assert result[1] == "consumer_discretionary"


def test_aimeike_maps_to_pharma():
    """爱美客 300896 归医药/医美，不归美容护理（去重决策）."""
    result = lookup_stock_cluster("300896")
    assert result is not None
    assert result[1] == "pharma"


def test_yiyi_lithium_maps_to_manufacturing():
    """亿纬锂能 300014 归制造/电力设备，不归 TMT（去重决策）."""
    result = lookup_stock_cluster("300014")
    assert result is not None
    assert result[1] == "manufacturing"


# ---------------------------------------------------------------------------
# cluster_resolver.resolve() and resolve_stock()
# ---------------------------------------------------------------------------

def test_known_industry_returns_correct_cluster():
    assert resolve("综合") == "conglomerate"


def test_unknown_industry_returns_conglomerate():
    assert resolve("某不存在的行业") == "conglomerate"


def test_none_returns_conglomerate():
    assert resolve(None) == "conglomerate"


def test_empty_string_returns_conglomerate():
    assert resolve("") == "conglomerate"


def test_whitespace_only_returns_conglomerate():
    assert resolve("   ") == "conglomerate"


def test_industry_with_whitespace_stripped():
    assert resolve("  综合  ") == "conglomerate"


def test_resolve_stock_local_hit_returns_static_entry():
    """本地映射表命中的股票不查远程，直接返回 (label, cluster)."""
    industry, cluster = resolve_stock("601728")
    assert industry == "通信运营"
    assert cluster == "utility_transport"


def test_resolve_stock_local_hit_for_bank():
    industry, cluster = resolve_stock("600036")
    assert cluster == "financial"
    assert industry == "股份制银行"


def test_resolve_stock_remote_fallback(monkeypatch: pytest.MonkeyPatch):
    """本地未命中时走远程 stock_individual_info_em，结果经 INDUSTRY_TO_CLUSTER 映射。"""
    from valor.strategy import cluster_resolver as cr

    monkeypatch.setattr(cr, "_fetch_industry_remote", lambda s: "银行")
    industry, cluster = resolve_stock("999999")
    assert industry == "银行"
    assert cluster == "financial"


def test_resolve_stock_remote_fallback_unknown_industry(monkeypatch: pytest.MonkeyPatch):
    """远程返回的行业名不在 INDUSTRY_TO_CLUSTER -> conglomerate."""
    from valor.strategy import cluster_resolver as cr

    monkeypatch.setattr(cr, "_fetch_industry_remote", lambda s: "某新行业")
    industry, cluster = resolve_stock("999999")
    assert industry == "某新行业"
    assert cluster == "conglomerate"


def test_resolve_stock_all_fail_returns_conglomerate(monkeypatch: pytest.MonkeyPatch):
    """本地未命中 + 远程失败 -> (None, conglomerate)."""
    from valor.strategy import cluster_resolver as cr

    monkeypatch.setattr(cr, "_fetch_industry_remote", lambda s: None)
    industry, cluster = resolve_stock("999999")
    assert industry is None
    assert cluster == "conglomerate"