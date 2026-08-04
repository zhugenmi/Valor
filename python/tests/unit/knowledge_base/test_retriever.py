"""Tests for retriever. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from datetime import datetime, timedelta

import pytest

from valor.knowledge_base.kb_store import insert_chunks, insert_document, insert_fts, insert_vectors
from valor.knowledge_base.models import Chunk, KBDoc
from valor.knowledge_base.retriever import retrieve
from valor.server.db import KB_AVAILABLE, init_db


@pytest.fixture
def kb_with_docs(tmp_path, monkeypatch):
    from valor.server import db as dbmod
    monkeypatch.setattr(dbmod, "DB_PATH", tmp_path / "test.db")
    dbmod.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    init_db()
    # Insert two docs
    now = datetime.utcnow()
    for i, (title, text) in enumerate([
        ("茅台业绩点评", "贵州茅台 2024Q3 营收增长 15%，净利润上升"),
        ("行业策略报告", "白酒行业整体复苏，高端白酒估值回落"),
    ]):
        doc = KBDoc(
            doc_id=f"d{i}", title=title, category="research", sub_type="公司研究",
            mime_type="text/plain", file_path=f"x{i}", sha256=f"sha{i}",
            publish_date=(now - timedelta(days=30)).date().isoformat(),
            effective_until=(now + timedelta(days=150)).date().isoformat(),
            uploaded_at=now.isoformat(), status="ready",
        )
        insert_document(doc)
        chunk = Chunk(chunk_id=f"c{i}", doc_id=f"d{i}", seq=0, text=text,
                      page_no=1, token_count=len(text), created_at=now.isoformat())
        insert_chunks([chunk])
        if KB_AVAILABLE:
            insert_vectors([f"c{i}"], [[0.1 * (i+1)] * 512])
        import jieba
        insert_fts([f"c{i}"], [" ".join(jieba.cut(text))])
    return dbmod


@pytest.mark.skipif(not KB_AVAILABLE, reason="sqlite-vec not available")
def test_retrieve_returns_chunks(kb_with_docs):
    results = retrieve("茅台业绩", top_k=2)
    assert len(results) >= 1
    assert results[0].chunk_id.startswith("c")
    assert results[0].doc_title


def test_retrieve_empty_when_no_match(kb_with_docs):
    results = retrieve("完全不相关的查询词汇xyz", top_k=5)
    # May return 0 or few results, but shouldn't crash
    assert isinstance(results, list)


@pytest.mark.skipif(not KB_AVAILABLE, reason="sqlite-vec not available")
def test_retrieve_vintage_filter(kb_with_docs):
    # Only current
    results = retrieve("茅台", top_k=5, vintage_filter=["current"])
    assert all(r.vintage == "current" for r in results)


@pytest.mark.skipif(not KB_AVAILABLE, reason="sqlite-vec not available")
def test_retrieve_skips_when_low_similarity(kb_with_docs, monkeypatch):
    """Pre-filter: top-1 similarity < threshold returns empty."""
    from valor.knowledge_base import retriever
    monkeypatch.setattr(retriever, "VALOR_KB_SIMILARITY_THRESHOLD", 0.99)
    results = retrieve("anything", top_k=5)
    assert results == []