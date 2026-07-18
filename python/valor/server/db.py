"""SQLite persistence for provider config and user profile.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

DB_PATH: Path = Path(__file__).resolve().parents[2] / "data" / "valor.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS provider_config (
    provider         TEXT PRIMARY KEY,
    api_key          TEXT,
    base_url         TEXT,
    is_default       INTEGER DEFAULT 0,
    default_model_id TEXT,
    updated_at       TEXT
);

CREATE TABLE IF NOT EXISTS provider_model (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    provider    TEXT NOT NULL,
    model_id    TEXT NOT NULL,
    model_name  TEXT NOT NULL,
    created_at  TEXT,
    UNIQUE(provider, model_id),
    FOREIGN KEY (provider) REFERENCES provider_config(provider) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_profile (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    content     TEXT NOT NULL,
    created_at  TEXT
);
"""


@contextmanager
def get_conn():
    """Yield a SQLite connection with WAL + foreign keys enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _seed_providers(conn: sqlite3.Connection) -> None:
    """Insert default rows for all registered LLM providers, adding any
    that are missing from the existing database (idempotent)."""
    try:
        from valor.adapters.llm.registry import list_providers

        known = list_providers()
    except Exception:
        known = []

    now = datetime.now(UTC).isoformat()
    has_existing = conn.execute("SELECT COUNT(*) FROM provider_config").fetchone()[0] > 0
    for name in known:
        conn.execute(
            "INSERT OR IGNORE INTO provider_config(provider, is_default, updated_at) "
            "VALUES (?, 0, ?)",
            (name, now),
        )
    # First provider becomes default only if no defaults exist yet
    if known and not has_existing:
        conn.execute(
            "UPDATE provider_config SET is_default=1 WHERE provider=?",
            (known[0],),
        )


def init_db() -> None:
    """Idempotent schema creation + provider seed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(_SCHEMA)
        _seed_providers(conn)


__all__ = ["DB_PATH", "get_conn", "init_db"]
