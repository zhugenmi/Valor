"""Unit tests for AkshareSQLiteCache.

Covers upsert/fetch round-trip, TTL expiration, dedup on key conflict,
column filtering, and record deletion.
"""

from pathlib import Path

import pytest

from valor.adapters.data.sqlite_cache import AkshareSQLiteCache


@pytest.fixture
def cache(tmp_path: Path) -> AkshareSQLiteCache:
    """Return a cache backed by a temp SQLite file."""
    return AkshareSQLiteCache(database_path=tmp_path / "test.db")


def test_upsert_and_fetch_round_trip(cache: AkshareSQLiteCache) -> None:
    """After upsert, fetch_records returns the stored record."""
    cache.upsert_records(
        table="realtime",
        records=[{"代码": "600519", "close": 10.0}],
        key_columns=["代码"],
    )
    result = cache.fetch_records(table="realtime")
    assert len(result) == 1
    assert result[0]["代码"] == "600519"
    assert result[0]["close"] == 10.0


def test_fetch_unknown_table_returns_empty(cache: AkshareSQLiteCache) -> None:
    """Fetching a table that does not exist returns an empty list."""
    result = cache.fetch_records(table="nonexistent")
    assert result == []


def test_ttl_expiration(cache: AkshareSQLiteCache) -> None:
    """Records are filtered out when ttl_seconds=0 (threshold is now)."""
    cache.upsert_records(
        table="realtime",
        records=[{"代码": "600519", "close": 10.0}],
        key_columns=["代码"],
    )
    result = cache.fetch_records(table="realtime", ttl_seconds=0)
    assert result == []


def test_upsert_dedup_on_key_conflict(cache: AkshareSQLiteCache) -> None:
    """Upserting with the same key replaces the row instead of inserting a duplicate."""
    cache.upsert_records(
        table="realtime",
        records=[{"代码": "600519", "close": 10.0}],
        key_columns=["代码"],
    )
    cache.upsert_records(
        table="realtime",
        records=[{"代码": "600519", "close": 20.0}],
        key_columns=["代码"],
    )
    result = cache.fetch_records(table="realtime")
    assert len(result) == 1
    assert result[0]["close"] == 20.0


def test_fetch_with_column_filter(cache: AkshareSQLiteCache) -> None:
    """fetch_records with a filter dict returns only matching rows."""
    cache.upsert_records(
        table="realtime",
        records=[
            {"代码": "600519", "close": 10.0},
            {"代码": "000001", "close": 5.0},
        ],
        key_columns=["代码"],
    )
    result = cache.fetch_records(table="realtime", filters={"代码": "600519"})
    assert len(result) == 1
    assert result[0]["代码"] == "600519"
    assert result[0]["close"] == 10.0


def test_delete_records(cache: AkshareSQLiteCache) -> None:
    """delete_records with a filter removes matching rows."""
    cache.upsert_records(
        table="realtime",
        records=[
            {"代码": "600519", "close": 10.0},
            {"代码": "000001", "close": 5.0},
        ],
        key_columns=["代码"],
    )
    cache.delete_records(table="realtime", filters={"代码": "600519"})
    result = cache.fetch_records(table="realtime")
    assert len(result) == 1
    assert result[0]["代码"] == "000001"
