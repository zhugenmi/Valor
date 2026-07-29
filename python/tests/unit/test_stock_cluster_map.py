"""Unit tests for stock_cluster_map static mapping.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
from valor.strategy.stock_cluster_map import STOCK_CLUSTER_MAP, lookup_stock_cluster


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
