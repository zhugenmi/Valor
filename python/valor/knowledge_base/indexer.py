"""Indexer: orchestrate parse -> chunk -> embed -> store. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

from pathlib import Path

import jieba

from valor.knowledge_base.chunker import chunk_document
from valor.knowledge_base.constants import CHUNK_STRATEGIES, ChunkStrategy
from valor.knowledge_base.kb_store import (
    insert_chunks,
    insert_fts,
    insert_vectors,
    update_document_status,
)
from valor.knowledge_base.parser import ParsedDocument


def _embed_batch(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """Thin wrapper so tests can monkeypatch."""
    from valor.knowledge_base.embedder import get_embedder

    return get_embedder().embed_batch(texts, batch_size=batch_size)


def _jieba_tokenize(text: str) -> str:
    """Tokenize for FTS5: jieba cut + space join."""
    return " ".join(jieba.cut(text))


def index_document(
    doc_id: str,
    parsed: ParsedDocument,
    strategy: ChunkStrategy,
    enable_correction: bool = True,
) -> int:
    """Chunk + embed + store. Returns chunk count."""
    chunks = chunk_document(parsed, strategy)
    if not chunks:
        update_document_status(doc_id, status="ready", error_msg=None, chunk_count=0)
        return 0

    # Assign doc_id to chunks
    for c in chunks:
        c.doc_id = doc_id

    # Insert chunks first
    insert_chunks(chunks)

    # Embed + insert vectors
    texts = [c.text for c in chunks]
    try:
        vectors = _embed_batch(texts)
        insert_vectors([c.chunk_id for c in chunks], vectors)
    except Exception:
        # Mark all as embed_failed, keep chunks
        from valor.server.db import get_conn

        with get_conn() as conn:
            conn.executemany(
                "UPDATE kb_chunks SET embed_failed = 1 WHERE chunk_id = ?",
                [(c.chunk_id,) for c in chunks],
            )
        for c in chunks:
            c.embed_failed = True

    # Insert FTS (jieba tokenized)
    fts_texts = [_jieba_tokenize(c.text) for c in chunks]
    insert_fts([c.chunk_id for c in chunks], fts_texts)

    # Update doc status
    update_document_status(doc_id, status="ready", error_msg=None, chunk_count=len(chunks))

    # Run corrector if enabled and disclosure doc
    if enable_correction:
        try:
            from valor.knowledge_base.corrector import verify_and_correct_for_doc

            verify_and_correct_for_doc(doc_id, parsed)
        except ImportError:
            pass  # corrector not yet implemented (Task 4.x)
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning("corrector failed for %s: %s", doc_id, exc)

    return len(chunks)


def reindex_document(doc_id: str, strategy_name: str | None = None) -> int:
    """Re-parse and re-index an existing document."""
    from valor.knowledge_base.kb_store import delete_document_chunks, get_document
    from valor.knowledge_base.parser import parse

    doc = get_document(doc_id)
    if doc is None:
        raise ValueError(f"document {doc_id} not found")
    # Delete existing chunks + vectors + fts
    delete_document_chunks(doc_id)
    # Re-parse
    parsed = parse(Path(doc.file_path), doc.mime_type)
    # Pick strategy
    if strategy_name and strategy_name in CHUNK_STRATEGIES:
        strategy = CHUNK_STRATEGIES[strategy_name]
    else:
        from valor.knowledge_base.constants import select_strategy

        strategy = select_strategy(doc.category, doc.sub_type)
    return index_document(doc_id, parsed, strategy, enable_correction=True)