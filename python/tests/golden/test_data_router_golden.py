"""Golden test: AkShareAdapter returns data matching a captured snapshot.

Replays a saved JSON snapshot of AkShare's realtime response for 600519
(Guizhou Maotai) to verify the adapter's parsing contract is stable.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from valor.adapters.data.akshare_adapter import AkShareAdapter

SNAPSHOT_DIR = Path(__file__).parent / "fixtures" / "akshare_snapshot"


@pytest.fixture
def mocked_spot_row():
    """Patch get_stock_spot_row to return a Series built from the snapshot."""
    snapshot_path = SNAPSHOT_DIR / "600519_realtime.json"
    with snapshot_path.open() as f:
        records = json.load(f)
    row = pd.Series(records[0])
    with patch(
        "valor.adapters.data.akshare_adapter.get_stock_spot_row",
        return_value=row,
    ):
        yield


@pytest.mark.asyncio
async def test_realtime_quote_matches_snapshot(mocked_spot_row):
    adapter = AkShareAdapter()
    df = await adapter.get_realtime_quote("600519")
    assert not df.empty
    assert "代码" in df.columns
    assert df.iloc[0]["代码"] == "600519"
    assert df.iloc[0]["名称"] == "贵州茅台"
    assert df.iloc[0]["最新价"] == 1500.0


@pytest.mark.asyncio
async def test_realtime_quote_empty_when_miss():
    with patch(
        "valor.adapters.data.akshare_adapter.get_stock_spot_row",
        return_value=None,
    ):
        adapter = AkShareAdapter()
        df = await adapter.get_realtime_quote("999999")
        assert df.empty
