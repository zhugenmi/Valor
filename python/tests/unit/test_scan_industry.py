"""Unit tests for scan_industry_distribution script.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pytest


# Ensure the scripts directory is importable
_SCRIPTS_DIR = Path(__file__).parent.parent.parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))


def _make_spot_df(industries: list[str | None]) -> pd.DataFrame:
    """Build a mock spot DataFrame with given industry values."""
    records: list[dict[str, Any]] = []
    for i, ind in enumerate(industries):
        code = f"{600000 + i:06d}"
        records.append({
            "代码": code,
            "名称": f"股票{code}",
            "行业": ind,
        })
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Tests for scan_distribution()
# ---------------------------------------------------------------------------

class TestScanDistribution:
    """Test the core scan_distribution function (mocked akshare)."""

    def test_basic_industry_counts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from scan_industry_distribution import scan_distribution

        df = _make_spot_df(["银行", "银行", "食品饮料", "食品饮料", "食品饮料"])
        result = scan_distribution(df)

        assert result["total_stocks"] == 5
        assert result["industry_counts"] == {"银行": 2, "食品饮料": 3}

    def test_unknown_industry_detected_as_unmapped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from scan_industry_distribution import scan_distribution

        df = _make_spot_df(["银行", "一个不存在的行业", "食品饮料"])
        result = scan_distribution(df)

        assert "一个不存在的行业" in result["unmapped_industries"]
        assert result["unmapped_industries"]["一个不存在的行业"] == 1

    def test_coverage_rate_calculation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from scan_industry_distribution import scan_distribution

        df = _make_spot_df(["银行", "银行", "未知行业X", "未知行业Y"])
        result = scan_distribution(df)

        assert result["total_stocks"] == 4
        assert result["coverage_rate"] == pytest.approx(0.5)  # 2/4 mapped

    def test_full_coverage(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from scan_industry_distribution import scan_distribution

        df = _make_spot_df(["银行", "食品饮料", "电子", "医药生物", "房地产"])
        result = scan_distribution(df)

        assert result["coverage_rate"] == 1.0
        assert result["unmapped_industries"] == {}

    def test_none_industry_treated_as_unknown(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from scan_industry_distribution import scan_distribution

        df = _make_spot_df(["银行", None, "食品饮料"])
        result = scan_distribution(df)

        assert "未知" in result["industry_counts"]
        assert result["industry_counts"]["未知"] == 1
        assert "未知" in result["unmapped_industries"]

    def test_empty_industries_list(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from scan_industry_distribution import scan_distribution

        df = _make_spot_df([None, None, None])
        result = scan_distribution(df)

        assert result["total_stocks"] == 3
        assert result["industry_counts"] == {"未知": 3}
        assert result["unmapped_industries"] == {"未知": 3}
        assert result["coverage_rate"] == 0.0


# ---------------------------------------------------------------------------
# Tests for cluster distribution
# ---------------------------------------------------------------------------

class TestClusterDistribution:
    """Test cluster-level aggregation."""

    def test_cluster_counts_aggregate_correctly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from scan_industry_distribution import scan_distribution

        df = _make_spot_df(["银行", "非银金融", "食品饮料", "食品饮料", "电子"])
        result = scan_distribution(df)

        assert "cluster_counts" in result
        assert result["cluster_counts"]["financial"] == 2
        assert result["cluster_counts"]["consumer_staples"] == 2
        assert result["cluster_counts"]["tmt"] == 1

    def test_unmapped_industries_not_in_cluster_counts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from scan_industry_distribution import scan_distribution

        df = _make_spot_df(["银行", "未知行业ABC"])
        result = scan_distribution(df)

        assert result["cluster_counts"]["financial"] == 1
        # unmapped industry should NOT appear in cluster_counts
        assert "conglomerate" not in result["cluster_counts"] or \
            result["cluster_counts"].get("conglomerate", 0) == 0


# ---------------------------------------------------------------------------
# Tests for write_output / main
# ---------------------------------------------------------------------------

class TestWriteOutput:
    """Test that the output JSON is written correctly."""

    def test_output_json_structure(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        from scan_industry_distribution import scan_distribution, write_output

        df = _make_spot_df(["银行", "银行", "食品饮料"])
        result = scan_distribution(df)

        out_file = tmp_path / "industry_distribution.json"
        write_output(result, out_file)

        assert out_file.exists()
        data = json.loads(out_file.read_text(encoding="utf-8"))
        assert data["total_stocks"] == 3
        assert data["industry_counts"] == {"银行": 2, "食品饮料": 1}
        assert "cluster_counts" in data
        assert "unmapped_industries" in data
        assert "coverage_rate" in data
        assert "known_aliases_in_mapping" in data

    def test_main_writes_file(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        import scan_industry_distribution as script

        df = _make_spot_df(["银行", "银行", "食品饮料", "电子", "医药生物"])

        def fake_spot() -> pd.DataFrame:
            return df

        monkeypatch.setattr(script.ak, "stock_zh_a_spot_em", fake_spot)

        out_file = tmp_path / "industry_distribution.json"
        script.main(output_path=out_file)

        assert out_file.exists()
        data = json.loads(out_file.read_text(encoding="utf-8"))
        assert data["total_stocks"] == 5
        assert data["coverage_rate"] == 1.0

    def test_main_empty_data_handled(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        import scan_industry_distribution as script

        def fake_spot() -> pd.DataFrame:
            return pd.DataFrame()

        monkeypatch.setattr(script.ak, "stock_zh_a_spot_em", fake_spot)
        out_file = tmp_path / "industry_distribution.json"

        # Should not raise, just return early
        script.main(output_path=out_file)
        # Since the script returns early on empty data, no file should be written
        # (or if it does, it should handle gracefully)

    def test_main_missing_columns_handled(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        import scan_industry_distribution as script

        df = pd.DataFrame({"代码": ["600001"], "名称": ["测试"]})  # no 行业 column
        monkeypatch.setattr(script.ak, "stock_zh_a_spot_em", lambda: df)
        out_file = tmp_path / "industry_distribution.json"

        # Should not raise, just return early
        script.main(output_path=out_file)