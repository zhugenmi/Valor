"""Golden test fixtures for industry cluster replay.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def snapshot_metrics():
    """Load captured financial metrics for a ticker from JSON snapshot.

    Returns a callable: snapshot_metrics(ticker, cluster) -> dict | None.
    Returns None if no snapshot exists, so the test can skip gracefully.

    When RUN_GOLDEN_TESTS=1 and snapshots are populated, replays the exact
    metrics that were captured during a prior successful run of
    get_financial_metrics(), enabling deterministic replay tests.
    """
    def _load(ticker: str, cluster: str) -> dict | None:
        snapshot_path = FIXTURES_DIR / "industry_cluster_snapshots" / f"{cluster}_{ticker}.json"
        if not snapshot_path.exists():
            return None
        with snapshot_path.open(encoding="utf-8") as f:
            return json.load(f)

    return _load