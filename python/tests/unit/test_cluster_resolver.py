"""Unit tests for cluster_resolver.resolve() and resolve_stock()."""
import pytest

from valor.strategy.cluster_resolver import resolve, resolve_stock


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


# ---------------------------------------------------------------------------
# resolve_stock
# ---------------------------------------------------------------------------


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