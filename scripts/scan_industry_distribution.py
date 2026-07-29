"""Scan full A-share market industry distribution.

Outputs JSON with industry -> count mapping for validating INDUSTRY_TO_CLUSTER coverage.

Usage:
    cd python && uv run python ../scripts/scan_industry_distribution.py

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import akshare as ak
import pandas as pd

from valor.strategy.cluster_resolver import resolve
from valor.strategy.industry_clusters import INDUSTRY_TO_CLUSTER


def scan_distribution(df: pd.DataFrame) -> dict[str, Any]:
    """Analyze industry and cluster distribution from a spot DataFrame.

    Args:
        df: DataFrame from ak.stock_zh_a_spot_em() with at least a "行业" column.

    Returns:
        Dict with keys: total_stocks, industry_counts, cluster_counts,
        unmapped_industries, coverage_rate, known_aliases_in_mapping.
    """
    if df is None or df.empty:
        return {
            "total_stocks": 0,
            "industry_counts": {},
            "cluster_counts": {},
            "unmapped_industries": {},
            "coverage_rate": 0.0,
            "known_aliases_in_mapping": list(INDUSTRY_TO_CLUSTER.keys()),
        }

    industry_col = _find_column(df, "行业")
    if industry_col is None:
        raise ValueError(f"DataFrame has no '行业' column. Columns: {list(df.columns)}")

    # Fill NaN industry values with "未知"
    industries = df[industry_col].fillna("未知")

    # Count per industry
    industry_counts: dict[str, int] = {}
    for ind in industries:
        ind_str = str(ind).strip()
        industry_counts[ind_str] = industry_counts.get(ind_str, 0) + 1

    # Cluster distribution and unmapped detection
    cluster_counts: dict[str, int] = {}
    unmapped: dict[str, int] = {}
    mapped_total = 0

    for industry, count in industry_counts.items():
        if industry in INDUSTRY_TO_CLUSTER:
            cluster = INDUSTRY_TO_CLUSTER[industry]
            cluster_counts[cluster] = cluster_counts.get(cluster, 0) + count
            mapped_total += count
        else:
            unmapped[industry] = count

    total = len(df)
    coverage = mapped_total / total if total > 0 else 0.0

    return {
        "total_stocks": total,
        "industry_counts": industry_counts,
        "cluster_counts": cluster_counts,
        "unmapped_industries": unmapped,
        "coverage_rate": coverage,
        "known_aliases_in_mapping": list(INDUSTRY_TO_CLUSTER.keys()),
    }


def write_output(result: dict[str, Any], out_path: Path) -> None:
    """Write the scan result to a JSON file.

    Args:
        result: Dict returned by scan_distribution().
        out_path: Destination file path.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main(output_path: Path | None = None) -> None:
    """Fetch spot data, scan distribution, and write output.

    Args:
        output_path: Optional override for the output file path.
                     Defaults to docs/strategy/industry_distribution.json.
    """
    print("Fetching full A-share spot data...")
    df = ak.stock_zh_a_spot_em()

    if df is None or df.empty:
        print("ERROR: empty data")
        return

    industry_col = _find_column(df, "行业")
    code_col = _find_column(df, "代码")
    if industry_col is None or code_col is None:
        print(f"ERROR: columns unexpected: {list(df.columns)}")
        return

    result = scan_distribution(df)

    out_path = output_path or (
        Path(__file__).resolve().parent.parent / "docs" / "strategy" / "industry_distribution.json"
    )
    write_output(result, out_path)

    print(f"Written to {out_path}")
    print(f"Coverage: {result['coverage_rate']:.1%} ({sum(result['cluster_counts'].values())}/{result['total_stocks']})")
    if result["unmapped_industries"]:
        print(f"Unmapped industries: {result['unmapped_industries']}")


def _find_column(df: pd.DataFrame, keyword: str) -> str | None:
    """Find the first column name containing the given keyword."""
    return next((c for c in df.columns if keyword in str(c)), None)


if __name__ == "__main__":
    main()