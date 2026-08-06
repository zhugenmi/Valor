"""Find chunk_id by doc_id + keyword phrase.

Used to (re)populate ground_truth_chunk_ids in the RAG eval dataset after
reindexing (chunk_ids change because they're content-hashed).

Search modes:
  1. Phrase search (default): chunks whose text contains the exact phrase.
  2. All-words search (--all-words): chunks whose text contains every word.
  3. Vector + rerank (--semantic): semantic search via the project retriever.

Usage:
    # Find chunks in a doc containing an exact phrase
    uv run python scripts/find_chunk_id.py \\
        --doc-id 02a9d94f-6765-41eb-9b23-4405bff32506 \\
        --phrase "1年期LPR为3.0%"

    # All-words mode (every word must appear, in any order)
    uv run python scripts/find_chunk_id.py \\
        --doc-id 02a9d94f-6765-41eb-9b23-4405bff32506 \\
        --all-words "1年期 LPR 3.0%" --limit 3

    # Search across all docs (no --doc-id)
    uv run python scripts/find_chunk_id.py --phrase "反洗钱" --limit 5

    # Output: chunk_id | page_no | heading_path | text excerpt
    # Exit code 0 if >=1 match, 1 if 0 matches.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure project root on sys.path when run as a script from python/
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from valor.server import db  # noqa: E402
from valor.server.db import get_conn  # noqa: E402


def search_phrase(doc_id: str | None, phrase: str, limit: int) -> list[dict]:
    """Return chunks whose text contains the exact phrase (newline-insensitive).

    PDFs often break lines mid-sentence, so we strip newlines before matching.
    """
    sql = (
        "SELECT chunk_id, doc_id, page_no, heading_path, text "
        "FROM kb_chunks WHERE REPLACE(text, char(10), '') LIKE ? "
    )
    params: list = [f"%{phrase}%"]
    if doc_id:
        sql += "AND doc_id = ? "
        params.append(doc_id)
    sql += "ORDER BY length(text) ASC LIMIT ?"
    params.append(limit)
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def search_all_words(doc_id: str | None, words: list[str], limit: int) -> list[dict]:
    """Return chunks whose text contains every word (any position)."""
    if not words:
        return []
    clauses = " AND ".join(["text LIKE ?"] * len(words))
    sql = f"SELECT chunk_id, doc_id, page_no, heading_path, text FROM kb_chunks WHERE {clauses} "
    params: list = [f"%{w}%" for w in words]
    if doc_id:
        sql += "AND doc_id = ? "
        params.append(doc_id)
    sql += "LIMIT ?"
    params.append(limit * 5)  # over-fetch, then rank by coverage
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    # Rank by number of distinct word occurrences (desc), then text length (asc)
    def score(r: dict) -> tuple[int, int]:
        text = r["text"]
        hits = sum(1 for w in words if w in text)
        return (-hits, len(text))
    rows.sort(key=score)
    return rows[:limit]


def search_semantic(query: str, top_k: int, doc_id: str | None) -> list[dict]:
    """Semantic search via project retriever (BM25+vec+RRF, no rerank)."""
    from valor.knowledge_base.retriever import retrieve
    results = retrieve(query, top_k=top_k * 3)
    if doc_id:
        results = [r for r in results if r.doc_id == doc_id]
    out = []
    for r in results[:top_k]:
        out.append({
            "chunk_id": r.chunk_id,
            "doc_id": r.doc_id,
            "page_no": r.page_no,
            "heading_path": r.heading_path,
            "text": r.text,
            "_score": r.score,
        })
    return out


def excerpt(text: str, phrase: str | None, width: int = 80) -> str:
    """Return a short excerpt around the phrase (or text start)."""
    text = text.replace("\n", " ").strip()
    if phrase and phrase in text:
        i = text.index(phrase)
        start = max(0, i - width // 2)
        end = min(len(text), i + len(phrase) + width // 2)
        return ("..." if start > 0 else "") + text[start:end] + ("..." if end < len(text) else "")
    return text[:width] + ("..." if len(text) > width else "")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--doc-id", default=None, help="Restrict search to one doc")
    p.add_argument("--phrase", default=None, help="Exact phrase to find in chunk text")
    p.add_argument("--all-words", default=None, help="Space-separated words; all must appear")
    p.add_argument("--semantic", default=None, help="Semantic query (uses retriever)")
    p.add_argument("--limit", type=int, default=5, help="Max results (default 5)")
    p.add_argument("--show-text", action="store_true", help="Print full text of each chunk")
    args = p.parse_args()

    if not db.KB_AVAILABLE:
        db.init_db()
    if not db.KB_AVAILABLE:
        print("ERROR: sqlite-vec not available", file=sys.stderr)
        sys.exit(2)

    if args.semantic:
        results = search_semantic(args.semantic, args.limit, args.doc_id)
        phrase_for_excerpt = args.semantic
    elif args.phrase:
        results = search_phrase(args.doc_id, args.phrase, args.limit)
        phrase_for_excerpt = args.phrase
    elif args.all_words:
        words = args.all_words.split()
        results = search_all_words(args.doc_id, words, args.limit)
        phrase_for_excerpt = words[0] if words else None
    else:
        p.error("Provide one of --phrase / --all-words / --semantic")

    if not results:
        print("No matches found.", file=sys.stderr)
        sys.exit(1)

    for r in results:
        score_str = f" score={r['_score']:.4f}" if "_score" in r else ""
        print(f"{r['chunk_id']} | p{r['page_no'] or '?'} | {r['heading_path'] or ''}{score_str}")
        if args.show_text:
            print(f"    TEXT: {r['text'][:500]}")
        else:
            print(f"    >> {excerpt(r['text'], phrase_for_excerpt)}")
        print()


if __name__ == "__main__":
    main()
