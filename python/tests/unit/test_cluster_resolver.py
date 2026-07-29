"""Unit tests for cluster_resolver.resolve()."""
from valor.strategy.cluster_resolver import resolve


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