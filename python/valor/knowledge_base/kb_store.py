"""SQLite CRUD for knowledge base tables. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from valor.knowledge_base.models import Chunk, CorrectionItem, KBDoc
from valor.server.db import get_conn
from valor.server import db as _db


def insert_document(doc: KBDoc) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO kb_documents
               (doc_id, title, category, sub_type, source, mime_type, file_path,
                file_size, sha256, page_count, chunk_count, publish_date,
                effective_until, ticker, uploaded_at, status, error_msg,
                chunk_strategy, meta_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (doc.doc_id, doc.title, doc.category, doc.sub_type, doc.source,
             doc.mime_type, doc.file_path, doc.file_size, doc.sha256,
             doc.page_count, doc.chunk_count, doc.publish_date,
             doc.effective_until, doc.ticker, doc.uploaded_at, doc.status,
             doc.error_msg, doc.chunk_strategy, doc.meta_json),
        )


def is_sha256_exists(sha256: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT doc_id FROM kb_documents WHERE sha256 = ?", (sha256,)
        ).fetchone()
        return row["doc_id"] if row else None


def get_document(doc_id: str) -> KBDoc | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM kb_documents WHERE doc_id = ?", (doc_id,)
        ).fetchone()
        return KBDoc.model_validate(dict(row)) if row else None


def list_documents(
    category: str | None,
    sub_type: str | None,
    ticker: str | None,
    limit: int,
    offset: int,
) -> tuple[list[KBDoc], int]:
    where: list[str] = []
    params: list[Any] = []
    if category:
        where.append("category = ?")
        params.append(category)
    if sub_type:
        where.append("sub_type = ?")
        params.append(sub_type)
    if ticker:
        where.append("ticker = ?")
        params.append(ticker)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    with get_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM kb_documents {clause}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM kb_documents {clause} ORDER BY datetime(uploaded_at) DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    return [KBDoc.model_validate(dict(r)) for r in rows], total


def update_document_status(
    doc_id: str,
    status: str,
    error_msg: str | None,
    chunk_count: int | None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """UPDATE kb_documents
               SET status = ?, error_msg = ?, chunk_count = COALESCE(?, chunk_count)
               WHERE doc_id = ?""",
            (status, error_msg, chunk_count, doc_id),
        )


def delete_document_chunks(doc_id: str) -> None:
    """Delete all chunks (and vec/fts entries) for a doc, keep the doc row."""
    with get_conn() as conn:
        chunk_ids = [
            r["chunk_id"]
            for r in conn.execute(
                "SELECT chunk_id FROM kb_chunks WHERE doc_id = ?", (doc_id,)
            ).fetchall()
        ]
        if chunk_ids:
            placeholders = ",".join("?" * len(chunk_ids))
            conn.execute("DELETE FROM kb_chunks WHERE doc_id = ?", (doc_id,))
            if _db.KB_AVAILABLE:
                conn.execute(
                    f"DELETE FROM kb_chunks_vec WHERE chunk_id IN ({placeholders})", chunk_ids
                )
            conn.execute(
                f"DELETE FROM kb_chunks_fts WHERE chunk_id IN ({placeholders})", chunk_ids
            )


def delete_document(doc_id: str) -> None:
    with get_conn() as conn:
        # kb_chunks ON DELETE CASCADE; vec/fts 手动删
        chunk_ids = [
            r["chunk_id"]
            for r in conn.execute(
                "SELECT chunk_id FROM kb_chunks WHERE doc_id = ?", (doc_id,)
            ).fetchall()
        ]
        if chunk_ids:
            placeholders = ",".join("?" * len(chunk_ids))
            conn.execute("DELETE FROM kb_chunks WHERE doc_id = ?", (doc_id,))
            if _db.KB_AVAILABLE:
                conn.execute(
                    f"DELETE FROM kb_chunks_vec WHERE chunk_id IN ({placeholders})",
                    chunk_ids,
                )
            conn.execute(
                f"DELETE FROM kb_chunks_fts WHERE chunk_id IN ({placeholders})",
                chunk_ids,
            )
        conn.execute("DELETE FROM kb_documents WHERE doc_id = ?", (doc_id,))


def insert_chunks(chunks: list[Chunk]) -> None:
    if not chunks:
        return
    with get_conn() as conn:
        conn.executemany(
            """INSERT INTO kb_chunks
               (chunk_id, doc_id, seq, text, page_no, heading_path, token_count,
                embed_failed, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            [(c.chunk_id, c.doc_id, c.seq, c.text, c.page_no, c.heading_path,
              c.token_count, int(c.embed_failed), c.created_at) for c in chunks],
        )


def get_chunks_by_doc(doc_id: str) -> list[Chunk]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM kb_chunks WHERE doc_id = ? ORDER BY seq", (doc_id,)
        ).fetchall()
    return [Chunk.model_validate(dict(r)) for r in rows]


def insert_vectors(chunk_ids: list[str], embeddings: list[list[float]]) -> None:
    if not chunk_ids:
        return
    if not _db.KB_AVAILABLE:
        return
    rows = [(cid, str(vec)) for cid, vec in zip(chunk_ids, embeddings)]
    with get_conn() as conn:
        conn.executemany(
            "INSERT INTO kb_chunks_vec (chunk_id, embedding) VALUES (?, ?)",
            rows,
        )


def insert_fts(chunk_ids: list[str], texts: list[str]) -> None:
    if not chunk_ids:
        return
    with get_conn() as conn:
        conn.executemany(
            "INSERT INTO kb_chunks_fts (chunk_id, text) VALUES (?, ?)",
            list(zip(chunk_ids, texts)),
        )


# ---------------------------------------------------------------------------
# corrections CRUD
# ---------------------------------------------------------------------------

def insert_correction(
    ticker: str,
    report_period: str,
    field_name: str,
    original_value: str | None,
    corrected_value: str,
    unit: str | None,
    source_doc_id: str,
    source_page: int | None,
    reason: str = "disclosure_authoritative",
) -> str:
    correction_id = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO kb_financial_corrections
               (correction_id, ticker, report_period, field_name, original_value,
                corrected_value, unit, source_doc_id, source_page, corrected_at, reason)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (correction_id, ticker, report_period, field_name, original_value,
             corrected_value, unit, source_doc_id, source_page,
             datetime.now(UTC).replace(tzinfo=None).isoformat(), reason),
        )
    return correction_id


def get_corrections(ticker: str, report_period: str) -> list[CorrectionItem]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM kb_financial_corrections WHERE ticker = ? AND report_period = ? "
            "ORDER BY datetime(corrected_at) DESC",
            (ticker, report_period),
        ).fetchall()
    return [CorrectionItem.model_validate(dict(r)) for r in rows]


def get_corrections_by_doc(doc_id: str) -> list[CorrectionItem]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM kb_financial_corrections WHERE source_doc_id = ? "
            "ORDER BY datetime(corrected_at) DESC",
            (doc_id,),
        ).fetchall()
    return [CorrectionItem.model_validate(dict(r)) for r in rows]


def delete_correction(correction_id: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM kb_financial_corrections WHERE correction_id = ?",
            (correction_id,),
        )