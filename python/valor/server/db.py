"""SQLite persistence for provider config and user profile.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

DB_PATH: Path = Path(__file__).resolve().parents[2] / "data" / "valor.db"

KB_AVAILABLE: bool = False

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

CREATE TABLE IF NOT EXISTS conversations (
    id           TEXT PRIMARY KEY,
    agent_name   TEXT NOT NULL,
    title        TEXT,
    status       TEXT NOT NULL,
    portfolio_id TEXT,
    ticker       TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    thread_id       TEXT,
    role            TEXT NOT NULL,
    event_type      TEXT,
    content         TEXT,
    created_at      TEXT NOT NULL,
    seq             INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_conv ON conversation_messages(conversation_id, seq);

-- ===== Knowledge Base =====
CREATE TABLE IF NOT EXISTS kb_documents (
    doc_id          TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    category        TEXT NOT NULL,
    sub_type        TEXT NOT NULL,
    source          TEXT,
    mime_type       TEXT NOT NULL,
    file_path       TEXT NOT NULL,
    file_size       INTEGER,
    sha256          TEXT NOT NULL UNIQUE,
    page_count      INTEGER,
    chunk_count     INTEGER,
    publish_date    TEXT,
    effective_until TEXT,
    ticker          TEXT,
    uploaded_at     TEXT NOT NULL,
    status          TEXT NOT NULL,
    error_msg       TEXT,
    chunk_strategy  TEXT,
    meta_json       TEXT
);
CREATE INDEX IF NOT EXISTS idx_kb_docs_cat ON kb_documents(category, sub_type);
CREATE INDEX IF NOT EXISTS idx_kb_docs_ticker ON kb_documents(ticker);
CREATE INDEX IF NOT EXISTS idx_kb_docs_publish ON kb_documents(publish_date);

CREATE TABLE IF NOT EXISTS kb_chunks (
    chunk_id        TEXT PRIMARY KEY,
    doc_id          TEXT NOT NULL REFERENCES kb_documents(doc_id) ON DELETE CASCADE,
    seq             INTEGER NOT NULL,
    text            TEXT NOT NULL,
    page_no         INTEGER,
    heading_path    TEXT,
    token_count     INTEGER,
    embed_failed    INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL,
    UNIQUE(doc_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_kb_chunks_doc ON kb_chunks(doc_id, seq);

CREATE TABLE IF NOT EXISTS kb_financial_corrections (
    correction_id   TEXT PRIMARY KEY,
    ticker          TEXT NOT NULL,
    report_period   TEXT NOT NULL,
    field_name      TEXT NOT NULL,
    original_value  TEXT,
    corrected_value TEXT NOT NULL,
    unit            TEXT,
    source_doc_id   TEXT NOT NULL REFERENCES kb_documents(doc_id) ON DELETE CASCADE,
    source_page     INTEGER,
    corrected_at    TEXT NOT NULL,
    reason          TEXT,
    UNIQUE(ticker, report_period, field_name, source_doc_id)
);
CREATE INDEX IF NOT EXISTS idx_kb_corr_lookup ON kb_financial_corrections(ticker, report_period);
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
    global KB_AVAILABLE
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        # Load sqlite-vec extension (best-effort, non-fatal)
        try:
            conn.enable_load_extension(True)
            import sqlite_vec
            conn.load_extension(sqlite_vec.loadable_path())
            conn.enable_load_extension(False)
            KB_AVAILABLE = True
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "sqlite-vec 加载失败，KB 模块将降级: %s", exc
            )
            KB_AVAILABLE = False

        conn.executescript(_SCHEMA)

        # Create vec0 virtual table only if extension loaded
        if KB_AVAILABLE:
            conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS kb_chunks_vec USING vec0("
                "chunk_id TEXT PRIMARY KEY, embedding FLOAT[512])"
            )

        # FTS5 is built-in, always create
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS kb_chunks_fts USING fts5("
            "chunk_id UNINDEXED, text, "
            "tokenize = 'unicode61 remove_diacritics 2')"
        )

        # Migration: add thread_id column if it doesn't exist
        cols = [
            row["name"]
            for row in conn.execute("PRAGMA table_info(conversation_messages)").fetchall()
        ]
        if "thread_id" not in cols:
            conn.execute(
                "ALTER TABLE conversation_messages ADD COLUMN thread_id TEXT"
            )
        _seed_providers(conn)


__all__ = ["DB_PATH", "KB_AVAILABLE", "get_conn", "init_db"]
