"""Thin wrapper exposing KB retrieval to agents and CLI.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
from __future__ import annotations

from valor.knowledge_base.retriever import retrieve


def search(
    query: str,
    top_k: int = 5,
    vintage_filter: list[str] | None = None,
) -> list[dict]:
    """Search KB and return top_k chunks as dicts. Empty list if KB unavailable or no match."""
    try:
        results = retrieve(query, top_k=top_k, vintage_filter=vintage_filter)
    except Exception:
        return []
    return [
        {
            "chunk_id": r.chunk_id,
            "doc_id": r.doc_id,
            "doc_title": r.doc_title,
            "publish_date": r.publish_date,
            "vintage": r.vintage,
            "page_no": r.page_no,
            "heading_path": r.heading_path,
            "text": r.text,
            "score": r.score,
        }
        for r in results
    ]
