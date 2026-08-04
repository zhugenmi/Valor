"""Tests for KB schema in server/db.py. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
import sqlite3

import pytest

from valor.server.db import KB_AVAILABLE, get_conn, init_db


def test_kb_available_flag_is_bool():
    assert isinstance(KB_AVAILABLE, bool)


def test_kb_documents_table_exists():
    init_db()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='kb_documents'"
        ).fetchall()
        assert len(rows) == 1


def test_kb_chunks_table_exists():
    init_db()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='kb_chunks'"
        ).fetchall()
        assert len(rows) == 1


def test_kb_financial_corrections_table_exists():
    init_db()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='kb_financial_corrections'"
        ).fetchall()
        assert len(rows) == 1


@pytest.mark.skipif(not KB_AVAILABLE, reason="sqlite-vec not available")
def test_kb_chunks_vec_virtual_table_exists():
    init_db()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='kb_chunks_vec'"
        ).fetchall()
        assert len(rows) == 1


def test_kb_chunks_fts_virtual_table_exists():
    init_db()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='kb_chunks_fts'"
        ).fetchall()
        assert len(rows) == 1


def test_kb_documents_sha256_unique():
    init_db()
    with get_conn() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO kb_documents (doc_id, title, category, sub_type, mime_type, "
                "file_path, sha256, uploaded_at, status) VALUES "
                "('d1','t','research','公司研究','application/pdf','p','abc','2026-01-01','indexing'),"
                "('d2','t','research','公司研究','application/pdf','p','abc','2026-01-01','indexing')"
            )