"""Tests for kb_store. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from datetime import UTC, datetime

import pytest

from valor.knowledge_base.kb_store import (
    delete_document,
    get_chunks_by_doc,
    get_document,
    insert_chunks,
    insert_document,
    insert_fts,
    insert_vectors,
    is_sha256_exists,
    list_documents,
    update_document_status,
)
from valor.knowledge_base.models import Chunk, KBDoc
from valor.server.db import KB_AVAILABLE, init_db


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    from valor.server import db as dbmod

    monkeypatch.setattr(dbmod, "DB_PATH", tmp_path / "test.db")
    dbmod.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    init_db()
    return dbmod


@pytest.fixture
def sample_doc():
    return KBDoc(
        doc_id="d1",
        title="测试研报",
        category="research",
        sub_type="公司研究",
        mime_type="application/pdf",
        file_path="data/kb_files/d1/test.pdf",
        sha256="abc123",
        uploaded_at=datetime.now(UTC).replace(tzinfo=None).isoformat(),
        status="indexing",
    )


def test_insert_and_get_document(fresh_db, sample_doc):
    insert_document(sample_doc)
    got = get_document("d1")
    assert got is not None
    assert got.title == "测试研报"
    assert got.status == "indexing"


def test_is_sha256_exists(fresh_db, sample_doc):
    assert is_sha256_exists("abc123") is None
    insert_document(sample_doc)
    assert is_sha256_exists("abc123") == "d1"


def test_list_documents_filter_by_category(fresh_db, sample_doc):
    insert_document(sample_doc)
    doc2 = sample_doc.model_copy(
        update={
            "doc_id": "d2",
            "sha256": "def456",
            "category": "disclosure",
            "sub_type": "年报",
        }
    )
    insert_document(doc2)
    items, total = list_documents(
        category="research", sub_type=None, ticker=None, limit=10, offset=0
    )
    assert total == 1
    assert items[0].doc_id == "d1"


def test_update_document_status(fresh_db, sample_doc):
    insert_document(sample_doc)
    update_document_status("d1", status="ready", error_msg=None, chunk_count=42)
    got = get_document("d1")
    assert got.status == "ready"
    assert got.chunk_count == 42


def test_insert_and_get_chunks(fresh_db, sample_doc):
    insert_document(sample_doc)
    chunks = [
        Chunk(
            chunk_id="c1",
            doc_id="d1",
            seq=0,
            text="第一段",
            page_no=1,
            heading_path="摘要",
            token_count=3,
        ),
        Chunk(
            chunk_id="c2",
            doc_id="d1",
            seq=1,
            text="第二段",
            page_no=1,
            heading_path="摘要",
            token_count=3,
        ),
    ]
    insert_chunks(chunks)
    got = get_chunks_by_doc("d1")
    assert len(got) == 2
    assert got[0].text == "第一段"


def test_delete_document_cascades_chunks(fresh_db, sample_doc):
    insert_document(sample_doc)
    insert_chunks([Chunk(chunk_id="c1", doc_id="d1", seq=0, text="x", token_count=1)])
    delete_document("d1")
    assert get_document("d1") is None
    assert get_chunks_by_doc("d1") == []


def test_insert_vectors(fresh_db, sample_doc):
    if not KB_AVAILABLE:
        pytest.skip("sqlite-vec not available")
    insert_document(sample_doc)
    insert_chunks([Chunk(chunk_id="c1", doc_id="d1", seq=0, text="x", token_count=1)])
    insert_vectors(["c1"], [[0.1] * 512])
    from valor.server.db import get_conn

    with get_conn() as conn:
        row = conn.execute(
            "SELECT chunk_id FROM kb_chunks_vec WHERE chunk_id = ?", ("c1",)
        ).fetchone()
        assert row is not None


def test_insert_fts(fresh_db, sample_doc):
    insert_document(sample_doc)
    insert_chunks(
        [Chunk(chunk_id="c1", doc_id="d1", seq=0, text="贵州茅台 业绩", token_count=5)]
    )
    insert_fts(["c1"], ["贵州 茅台 业绩"])  # jieba 分词后
    from valor.server.db import get_conn

    with get_conn() as conn:
        row = conn.execute(
            "SELECT chunk_id FROM kb_chunks_fts WHERE kb_chunks_fts MATCH '贵州' ORDER BY rank"
        ).fetchone()
        assert row is not None
        assert row["chunk_id"] == "c1"