"""Retriever: BM25 + vector + RRF + rerank + time decay. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import UTC, datetime

import jieba

from valor.server import db
from valor.server.db import get_conn

VALOR_KB_SIMILARITY_THRESHOLD = float(os.getenv("VALOR_KB_SIMILARITY_THRESHOLD", "0.30"))
VALOR_KB_BM25_K = int(os.getenv("VALOR_KB_BM25_K", "30"))
VALOR_KB_VEC_K = int(os.getenv("VALOR_KB_VEC_K", "30"))
VALOR_KB_RRF_K = int(os.getenv("VALOR_KB_RRF_K", "10"))
VALOR_KB_RRF_W_BM25 = float(os.getenv("VALOR_KB_RRF_W_BM25", "0.3"))
VALOR_KB_RRF_W_VEC = float(os.getenv("VALOR_KB_RRF_W_VEC", "0.7"))

# FTS5 query syntax reserves these chars; strip them to avoid "syntax error"
# when user queries contain punctuation like ?, comma, *, etc.
# Includes both ASCII and full-width (Chinese) variants.
_FTS5_SPECIAL_CHARS = '"*:()[]{}^~+-/\\?，？、。；：！!？'

_RERANKER = None
_RERANKER_LOCK = threading.Lock()


@dataclass
class ChunkResult:
    chunk_id: str
    doc_id: str
    text: str
    page_no: int | None = None
    heading_path: str | None = None
    score: float = 0.0
    similarity: float = 0.0
    doc_title: str = ""
    publish_date: str | None = None
    effective_until: str | None = None
    vintage: str = "current"


def get_reranker():
    """Lazy singleton reranker (bge-reranker-v2-m3)."""
    global _RERANKER
    if _RERANKER is None:
        with _RERANKER_LOCK:
            if _RERANKER is None:
                from sentence_transformers import CrossEncoder
                model_name = os.getenv("VALOR_KB_RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
                _RERANKER = CrossEncoder(model_name)
    return _RERANKER


def retrieve(
    query: str,
    top_k: int = 5,
    vintage_filter: list[str] | None = None,
    include_obsolete: bool = False,
) -> list[ChunkResult]:
    """Main retrieval pipeline. Returns empty list if pre-filter rejects."""
    if not db.KB_AVAILABLE:
        return []

    # Stage 2: pre-filter (top-1 vector similarity)
    top1 = _vec_search(query, k=1)
    if not top1 or top1[0].similarity < VALOR_KB_SIMILARITY_THRESHOLD:
        return []

    # Stage 3: full RAG
    bm25_hits = _bm25_search(query, k=VALOR_KB_BM25_K)
    vec_hits = _vec_search(query, k=VALOR_KB_VEC_K)
    fused = _rrf(bm25_hits, vec_hits, k=VALOR_KB_RRF_K)

    # Time decay + vintage filter
    now = datetime.now(UTC).replace(tzinfo=None)
    fused = _apply_time_decay(fused, now)
    fused = _filter_vintage(fused, vintage_filter, include_obsolete, now)

    # Rerank
    if fused:
        try:
            fused = _rerank(query, fused, top_k=top_k)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("rerank failed, using RRF order: %s", exc)
            fused = fused[:top_k]

    # Enrich with doc metadata
    return _enrich(fused)


def _bm25_search(query: str, k: int) -> list[ChunkResult]:
    tokens = " ".join(jieba.cut(query))
    # Sanitize: keep only CJK chars, alphanumeric, and whitespace.
    # FTS5 reserves many punctuation chars (, ? " * : etc.) and throws
    # "syntax error near ..." when user queries contain them.
    tokens = "".join(
        c if (c.isalnum() or c.isspace() or "一" <= c <= "鿿") else " "
        for c in tokens
    )
    tokens = " ".join(tokens.split())
    if not tokens.strip():
        return []
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT chunk_id, bm25(kb_chunks_fts) AS score "
            "FROM kb_chunks_fts WHERE kb_chunks_fts MATCH ? ORDER BY score LIMIT ?",
            (tokens, k),
        ).fetchall()
    return [ChunkResult(chunk_id=r["chunk_id"], doc_id="", text="", score=-r["score"]) for r in rows]


def _vec_search(query: str, k: int) -> list[ChunkResult]:
    from valor.knowledge_base.embedder import get_embedder
    qvec = get_embedder().embed(query)
    vec_str = str(qvec)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT chunk_id, distance FROM kb_chunks_vec "
            "WHERE embedding MATCH ? AND k = ? ORDER BY distance",
            (vec_str, k),
        ).fetchall()
    results = []
    for r in rows:
        # bge embeddings are normalized; cosine sim = 1 - distance^2 / 2 (approx for normalized)
        sim = max(0.0, 1.0 - r["distance"] / 2)
        results.append(ChunkResult(chunk_id=r["chunk_id"], doc_id="", text="",
                                    similarity=sim, score=sim))
    return results


def _rrf(
    bm25_hits: list[ChunkResult],
    vec_hits: list[ChunkResult],
    k: int,
    c: int = 60,
    w_bm25: float | None = None,
    w_vec: float | None = None,
) -> list[ChunkResult]:
    """Reciprocal Rank Fusion with optional weighted BM25/vector scores.

    Weighted RRF: score(d) = w_bm25 / (c + rank_bm25) + w_vec / (c + rank_vec)

    Weights default to VALOR_KB_RRF_W_BM25 (0.3) and VALOR_KB_RRF_W_VEC (0.7),
    favoring vector retrieval (better semantic recall for Chinese finance docs).
    Set both to 0.5 for classic equal-weight RRF.
    """
    if w_bm25 is None:
        w_bm25 = VALOR_KB_RRF_W_BM25
    if w_vec is None:
        w_vec = VALOR_KB_RRF_W_VEC
    scores: dict[str, float] = {}
    meta: dict[str, ChunkResult] = {}
    for rank, hit in enumerate(bm25_hits):
        scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + w_bm25 / (c + rank)
        meta.setdefault(hit.chunk_id, hit)
    for rank, hit in enumerate(vec_hits):
        scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + w_vec / (c + rank)
        meta.setdefault(hit.chunk_id, hit)
    ranked = sorted(scores.items(), key=lambda x: -x[1])[:k]
    out = []
    for cid, score in ranked:
        m = meta[cid]
        m.score = score
        out.append(m)
    return out


def _apply_time_decay(hits: list[ChunkResult], now: datetime) -> list[ChunkResult]:
    """Apply time decay based on effective_until. Requires doc metadata."""
    # We need effective_until per chunk; fetch in batch
    if not hits:
        return hits
    chunk_ids = [h.chunk_id for h in hits]
    placeholders = ",".join("?" * len(chunk_ids))
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT c.chunk_id, d.effective_until, d.meta_json "
            f"FROM kb_chunks c JOIN kb_documents d ON c.doc_id = d.doc_id "
            f"WHERE c.chunk_id IN ({placeholders})",
            chunk_ids,
        ).fetchall()
    eu_map = {r["chunk_id"]: r["effective_until"] for r in rows}
    meta_map = {r["chunk_id"]: r["meta_json"] for r in rows}
    for h in hits:
        eu = eu_map.get(h.chunk_id)
        h.effective_until = eu
        meta_json = meta_map.get(h.chunk_id) or "{}"
        meta = json.loads(meta_json) if isinstance(meta_json, str) else (meta_json or {})
        if meta.get("vintage_override") == "obsolete":
            h.vintage = "obsolete"
            continue
        if not eu:
            h.vintage = "legacy"
            decay = 0.4
        else:
            try:
                eu_dt = datetime.fromisoformat(eu)
            except (ValueError, TypeError):
                h.vintage = "legacy"
                decay = 0.4
                continue
            days_overdue = (now - eu_dt).days
            if days_overdue <= 0:
                h.vintage = "current"
                decay = 1.0
            elif days_overdue <= 365:
                h.vintage = "recent"
                decay = 0.7
            else:
                h.vintage = "legacy"
                decay = 0.4
        h.score *= decay
    return sorted(hits, key=lambda x: -x.score)


def _filter_vintage(
    hits: list[ChunkResult],
    vintage_filter: list[str] | None,
    include_obsolete: bool,
    now: datetime,
) -> list[ChunkResult]:
    if include_obsolete and not vintage_filter:
        return hits
    out = []
    for h in hits:
        if h.vintage == "obsolete" and not include_obsolete:
            continue
        if vintage_filter and h.vintage not in vintage_filter:
            continue
        out.append(h)
    return out


def _rerank(query: str, candidates: list[ChunkResult], top_k: int) -> list[ChunkResult]:
    """Cross-encoder rerank. Requires text fetched from kb_chunks."""
    if not candidates:
        return []
    chunk_ids = [c.chunk_id for c in candidates]
    placeholders = ",".join("?" * len(chunk_ids))
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT chunk_id, text, page_no, heading_path, doc_id "
            f"FROM kb_chunks WHERE chunk_id IN ({placeholders})",
            chunk_ids,
        ).fetchall()
    text_map = {r["chunk_id"]: (r["text"], r["page_no"], r["heading_path"], r["doc_id"]) for r in rows}
    pairs = []
    for c in candidates:
        text, page_no, heading_path, doc_id = text_map.get(c.chunk_id, ("", None, None, ""))
        c.text = text
        c.page_no = page_no
        c.heading_path = heading_path
        c.doc_id = doc_id
        pairs.append((query, text))
    reranker = get_reranker()
    scores = reranker.predict(pairs)
    for c, s in zip(candidates, scores):
        c.score = float(s)
    candidates.sort(key=lambda x: -x.score)
    return candidates[:top_k]


def _enrich(hits: list[ChunkResult]) -> list[ChunkResult]:
    """Fill in doc_title, publish_date from kb_documents."""
    if not hits:
        return hits
    doc_ids = list({h.doc_id for h in hits if h.doc_id})
    if not doc_ids:
        return hits
    placeholders = ",".join("?" * len(doc_ids))
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT doc_id, title, publish_date, effective_until FROM kb_documents "
            f"WHERE doc_id IN ({placeholders})",
            doc_ids,
        ).fetchall()
    doc_map = {r["doc_id"]: r for r in rows}
    for h in hits:
        d = doc_map.get(h.doc_id)
        if d:
            h.doc_title = d["title"]
            h.publish_date = d["publish_date"]
            h.effective_until = d["effective_until"]
    return hits