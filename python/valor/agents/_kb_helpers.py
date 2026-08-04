"""Shared KB helpers for agents. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

import re

from valor.core.protocols import Citation


def build_kb_section(kb_ctx: dict) -> str:
    """Build KB context section for user message. Empty if skipped/no chunks."""
    if not kb_ctx or kb_ctx.get("skipped"):
        return ""
    chunks = kb_ctx.get("chunks") or []
    if not chunks:
        return ""
    lines = ["## 知识库参考（按相关性排序）"]
    for i, c in enumerate(chunks, 1):
        lines.append(
            f"[C{i}]《{c.get('doc_title', '')}》"
            f"(发布: {c.get('publish_date', '未知')}, 时效: {c.get('vintage', 'unknown')})"
        )
        lines.append(f"  正文：{c.get('text', '')}")
    return "\n".join(lines)


def extract_citations(text: str, kb_ctx: dict) -> list[Citation]:
    """Extract [Cn] references from LLM output and map to chunks."""
    if not kb_ctx or kb_ctx.get("skipped"):
        return []
    chunks = kb_ctx.get("chunks") or []
    if not chunks:
        return []
    refs = set(re.findall(r"\[C(\d+)\]", text))
    citations = []
    for ref in sorted(refs, key=int):
        idx = int(ref) - 1
        if 0 <= idx < len(chunks):
            c = chunks[idx]
            citations.append(Citation(
                chunk_id=c.get("chunk_id", ""),
                doc_id=c.get("doc_id", ""),
                doc_title=c.get("doc_title", ""),
                publish_date=c.get("publish_date", ""),
                vintage=c.get("vintage", "unknown"),
                page_no=c.get("page_no"),
                cited_text=c.get("text", "")[:200],
            ))
    return citations