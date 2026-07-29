"""Golden replay tests for 10 industry clusters.

Requires pre-captured metric snapshots. Run manually with:
    cd python && RUN_GOLDEN_TESTS=1 uv run pytest tests/golden/test_industry_cluster_replay.py -v

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
import json
import os
from pathlib import Path

import pytest

from valor.agents.fundamentals import fundamentals_agent

CLUSTER_REPRESENTATIVES = [
    ("financial", "600036", "银行"),
    ("real_estate", "000002", "房地产"),
    ("cyclical_resource", "601088", "煤炭"),
    ("manufacturing", "000333", "家用电器"),
    ("consumer_staples", "600519", "食品饮料"),
    ("consumer_discretionary", "000651", "家用电器"),
    ("pharma", "600276", "医药生物"),
    ("tmt", "002415", "电子"),
    ("utility_transport", "600900", "电力"),
    ("conglomerate", "600642", "综合"),
]

GOLDEN_DIR = Path(__file__).parent / "snapshots" / "industry_clusters"


def _make_state(cluster, industry, metrics):
    return {
        "messages": [],
        "data": {"financial_metrics": [metrics], "cluster": cluster, "industry": industry},
        "metadata": {"show_reasoning": False},
    }


@pytest.mark.skipif(not os.getenv("RUN_GOLDEN_TESTS"), reason="set RUN_GOLDEN_TESTS=1 to run")
@pytest.mark.parametrize("cluster,ticker,industry", CLUSTER_REPRESENTATIVES)
def test_cluster_replay(cluster, ticker, industry, snapshot_metrics):
    """Replay each cluster's representative metrics, verify signal stability."""
    metrics = snapshot_metrics(ticker, cluster)
    if metrics is None:
        pytest.skip(f"No snapshot for {cluster}/{ticker} -- capture metrics first")

    result = fundamentals_agent(_make_state(cluster, industry, metrics))
    msg = json.loads(result["messages"][0].content)

    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_path = GOLDEN_DIR / f"{cluster}_{ticker}.json"
    if snapshot_path.exists():
        expected = json.loads(snapshot_path.read_text(encoding="utf-8"))
        assert msg["signal"] == expected["signal"], f"{cluster}: signal drift"
        assert msg["industry_profile"]["cluster"] == cluster
    else:
        # First run: record the snapshot
        snapshot_path.write_text(
            json.dumps(
                {"signal": msg["signal"], "confidence": msg["confidence"]},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        pytest.skip(f"Snapshot recorded for {cluster}, re-run to verify")