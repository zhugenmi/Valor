"""Tests for indexer. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from datetime import UTC, datetime

import pytest

from valor.knowledge_base.constants import CHUNK_STRATEGIES
from valor.knowledge_base.indexer import index_document
from valor.knowledge_base.kb_store import get_chunks_by_doc, insert_document
from valor.knowledge_base.models import KBDoc
from valor.knowledge_base.parser import ParsedDocument, ParsedPage
from valor.server.db import init_db


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    from valor.server import db as dbmod

    monkeypatch.setattr(dbmod, "DB_PATH", tmp_path / "test.db")
    dbmod.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    init_db()
    return dbmod


def test_index_document_writes_chunks_and_vectors(fresh_db):
    doc = KBDoc(
        doc_id="d1",
        title="t",
        category="research",
        sub_type="公司研究",
        mime_type="text/plain",
        file_path="x",
        sha256="abc",
        uploaded_at=datetime.now(UTC).replace(tzinfo=None).isoformat(),
    )
    insert_document(doc)
    parsed = ParsedDocument(
        file_path="x",
        mime_type="text/plain",
        pages=[ParsedPage(page_no=1, text="第一段内容。第二段内容。")],
        full_text="第一段内容。第二段内容。",
    )
    strategy = CHUNK_STRATEGIES["research"]
    count = index_document("d1", parsed, strategy, enable_correction=False)
    assert count >= 1
    chunks = get_chunks_by_doc("d1")
    assert len(chunks) == count
    # All chunks should have vector (skip if vec unavailable)
    from valor.server.db import KB_AVAILABLE

    if KB_AVAILABLE:
        from valor.server.db import get_conn

        with get_conn() as conn:
            rows = conn.execute(
                "SELECT COUNT(*) FROM kb_chunks_vec WHERE chunk_id IN "
                "(SELECT chunk_id FROM kb_chunks WHERE doc_id=?)",
                ("d1",),
            ).fetchone()
            assert rows[0] == count


def test_index_document_marks_embed_failed_gracefully(fresh_db, monkeypatch):
    """If embedder fails for a chunk, mark embed_failed but keep chunk."""
    doc = KBDoc(
        doc_id="d2",
        title="t",
        category="research",
        sub_type="公司研究",
        mime_type="text/plain",
        file_path="x",
        sha256="def",
        uploaded_at=datetime.now(UTC).replace(tzinfo=None).isoformat(),
    )
    insert_document(doc)
    parsed = ParsedDocument(
        file_path="x",
        mime_type="text/plain",
        pages=[ParsedPage(page_no=1, text="内容")],
        full_text="内容",
    )
    # Mock embedder to raise
    from valor.knowledge_base import indexer

    def boom(texts, batch_size=32):
        raise RuntimeError("embed failed")

    monkeypatch.setattr(indexer, "_embed_batch", boom)
    count = index_document("d2", parsed, CHUNK_STRATEGIES["research"], enable_correction=False)
    assert count >= 1
    chunks = get_chunks_by_doc("d2")
    assert all(c.embed_failed for c in chunks)