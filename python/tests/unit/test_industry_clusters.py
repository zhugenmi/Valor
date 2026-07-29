"""Unit tests for industry cluster configuration."""
from valor.strategy.industry_clusters import (
    INDUSTRY_CLUSTERS,
)


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


def test_all_clusters_weights_sum_to_one():
    """每集群维度权重和 = 1.0."""
    for key, cluster in INDUSTRY_CLUSTERS.items():
        total = sum(d.weight for d in cluster.dimensions)
        assert abs(total - 1.0) < 1e-6, f"{key} weights sum={total}"