"""Document chunker with 7 type-specific strategies.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Iterable

from valor.knowledge_base.constants import ChunkStrategy
from valor.knowledge_base.models import Chunk
from valor.knowledge_base.parser import HeadingNode, ParsedDocument, ParsedTable


def chunk_document(parsed: ParsedDocument, strategy: ChunkStrategy) -> list[Chunk]:
    """Chunk a parsed document according to strategy."""
    mode = strategy.split_mode
    if mode == "clause":
        chunks = _chunk_clause(parsed, strategy)
    elif mode == "table_aware":
        chunks = _chunk_table_aware(parsed, strategy)
    elif mode in ("semantic", "semantic_fallback"):
        chunks = _chunk_semantic(parsed, strategy, force_fallback=(mode == "semantic_fallback"))
    else:
        chunks = _chunk_fixed(parsed, strategy)
    # Assign seq + chunk_id
    for i, c in enumerate(chunks):
        c.seq = i
        if not c.chunk_id:
            c.chunk_id = str(uuid.uuid4())
        if not c.created_at:
            c.created_at = datetime.utcnow().isoformat()
    return chunks


def _split_recursive(text: str, separators: list[str], chunk_size: int, overlap: int) -> list[str]:
    """Recursive splitter: try separators in priority order."""
    if len(text) <= chunk_size:
        return [text] if text.strip() else []
    for i, sep in enumerate(separators):
        if sep in text:
            parts = text.split(sep)
            chunks: list[str] = []
            current = ""
            for p in parts:
                candidate = (current + sep + p) if current else p
                if len(candidate) <= chunk_size:
                    current = candidate
                else:
                    if current:
                        chunks.append(current)
                    # Recurse on the over-sized part with next separator
                    if len(p) > chunk_size and i + 1 < len(separators):
                        chunks.extend(_split_recursive(p, separators[i+1:], chunk_size, overlap))
                    else:
                        current = p
            if current:
                chunks.append(current)
            # Apply overlap by prepending tail of previous chunk
            if overlap > 0 and len(chunks) > 1:
                merged = [chunks[0]]
                for c in chunks[1:]:
                    tail = merged[-1][-overlap:] if len(merged[-1]) >= overlap else merged[-1]
                    merged.append(tail + c)
                chunks = merged
            return [c for c in chunks if c.strip()]
    # No separator found, hard split
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size - overlap)]


def _chunk_semantic(parsed: ParsedDocument, strategy: ChunkStrategy,
                    force_fallback: bool = False) -> list[Chunk]:
    """Semantic: split by top-level headings, then recursive within section."""
    chunks: list[Chunk] = []
    # If we have heading tree, split by top-level headings
    if parsed.heading_tree:
        sections = _split_text_by_headings(parsed.full_text, parsed.heading_tree)
    else:
        sections = [(None, 1, parsed.full_text)]

    for heading_path, page_no, section_text in sections:
        size = strategy.chunk_size
        if force_fallback and len(section_text) > size * 1.5:
            # Force fallback: use all separators including last
            parts = _split_recursive(section_text, strategy.separators, size, strategy.overlap)
        else:
            parts = _split_recursive(section_text, strategy.separators, size, strategy.overlap)
        for p in parts:
            chunks.append(Chunk(
                chunk_id="", doc_id="", seq=0, text=p,
                page_no=page_no, heading_path=heading_path,
                token_count=len(p),
            ))
    # Add tables as separate chunks
    if strategy.table_mode == "keep_whole":
        for tbl in parsed.tables:
            tbl_md = _table_to_markdown(tbl)
            if tbl_md.strip():
                chunks.append(Chunk(
                    chunk_id="", doc_id="", seq=0, text=tbl_md,
                    page_no=tbl.page_no, heading_path="[表格]",
                    token_count=len(tbl_md),
                ))
    return chunks


def _chunk_clause(parsed: ParsedDocument, strategy: ChunkStrategy) -> list[Chunk]:
    """Clause: split by 第X条 pattern."""
    pattern = strategy.separators[0] if strategy.separators else r"第[一二三四五六七八九十百千\d]+条"
    parts = re.split(f"({pattern})", parsed.full_text)
    chunks: list[Chunk] = []
    i = 1
    while i < len(parts):
        prefix = parts[i]
        body = parts[i+1] if i+1 < len(parts) else ""
        text = prefix + body
        if len(text) > strategy.chunk_size:
            sub_parts = _split_recursive(text, ["。", "；"], strategy.chunk_size, 0)
            for sp in sub_parts:
                chunks.append(Chunk(chunk_id="", doc_id="", seq=0, text=sp,
                                    page_no=1, token_count=len(sp)))
        else:
            chunks.append(Chunk(chunk_id="", doc_id="", seq=0, text=text,
                                page_no=1, token_count=len(text)))
        i += 2
    if not chunks:
        # No clause pattern matched, fallback to fixed
        return _chunk_fixed(parsed, strategy)
    return chunks


def _chunk_table_aware(parsed: ParsedDocument, strategy: ChunkStrategy) -> list[Chunk]:
    """Table-aware: tables as separate chunks, text by semantic."""
    chunks: list[Chunk] = []
    # Tables
    for tbl in parsed.tables:
        tbl_md = _table_to_markdown(tbl)
        if not tbl_md.strip():
            continue
        if strategy.table_mode == "row_split" and len(tbl_md) > 1500:
            # Split by rows, repeat header
            header = tbl.rows[0] if tbl.rows else []
            rows = tbl.rows[1:] if len(tbl.rows) > 1 else []
            for i in range(0, len(rows), 20):
                batch = rows[i:i+20]
                batch_md = _table_to_markdown(tbl.__class__(
                    page_no=tbl.page_no, rows=[header] + batch))
                chunks.append(Chunk(chunk_id="", doc_id="", seq=0, text=batch_md,
                                    page_no=tbl.page_no, heading_path="[表格]",
                                    token_count=len(batch_md)))
        else:
            chunks.append(Chunk(chunk_id="", doc_id="", seq=0, text=tbl_md,
                                page_no=tbl.page_no, heading_path="[表格]",
                                token_count=len(tbl_md)))
    # Non-table text: strip out table lines from full_text
    text_without_tables = _strip_tables(parsed.full_text, parsed.tables)
    text_chunks = _split_recursive(text_without_tables, strategy.separators,
                                    strategy.chunk_size, strategy.overlap)
    for p in text_chunks:
        chunks.append(Chunk(chunk_id="", doc_id="", seq=0, text=p,
                            page_no=1, token_count=len(p)))
    return chunks


def _chunk_fixed(parsed: ParsedDocument, strategy: ChunkStrategy) -> list[Chunk]:
    """Fixed: pure recursive split, no heading awareness."""
    parts = _split_recursive(parsed.full_text, strategy.separators,
                              strategy.chunk_size, strategy.overlap)
    chunks = [Chunk(chunk_id="", doc_id="", seq=0, text=p, page_no=1,
                    token_count=len(p)) for p in parts]
    # Tables
    if strategy.table_mode == "keep_whole":
        for tbl in parsed.tables:
            tbl_md = _table_to_markdown(tbl)
            if tbl_md.strip():
                chunks.append(Chunk(chunk_id="", doc_id="", seq=0, text=tbl_md,
                                    page_no=tbl.page_no, heading_path="[表格]",
                                    token_count=len(tbl_md)))
    return chunks


def _split_text_by_headings(text: str, headings: list[HeadingNode]) -> list[tuple[str | None, int, str]]:
    """Split text by heading positions. Returns [(heading_path, page_no, section_text)]."""
    if not headings:
        return [(None, 1, text)]
    # Find heading text positions in the document
    sections: list[tuple[str | None, int, str]] = []
    positions: list[tuple[int, str, int]] = []
    for h in headings:
        idx = text.find(h.text)
        if idx >= 0:
            positions.append((idx, h.text, h.page_no))
    positions.sort(key=lambda x: x[0])
    if not positions:
        return [(None, 1, text)]
    # Prefix before first heading
    if positions[0][0] > 0:
        prefix = text[:positions[0][0]].strip()
        # Skip markdown heading markers (e.g., "#", "##")
        if prefix and not re.match(r"^#+$", prefix):
            sections.append((None, 1, prefix))
    for i, (idx, h_text, page_no) in enumerate(positions):
        end = positions[i+1][0] if i+1 < len(positions) else len(text)
        section = text[idx:end].strip()
        if section:
            sections.append((h_text, page_no, section))
    return sections


def _table_to_markdown(tbl: ParsedTable) -> str:
    """Convert table to markdown syntax."""
    if not tbl.rows:
        return ""
    lines = []
    for i, row in enumerate(tbl.rows):
        cells = [str(c).replace("|", "\\|").replace("\n", " ") for c in row]
        lines.append("| " + " | ".join(cells) + " |")
        if i == 0:
            lines.append("|" + "---|" * len(row))
    return "\n".join(lines)


def _strip_tables(text: str, tables: Iterable[ParsedTable]) -> str:
    """Remove table row lines from text (lines starting with |)."""
    lines = text.splitlines()
    kept = [ln for ln in lines if not ln.lstrip().startswith("|")]
    return "\n".join(kept)