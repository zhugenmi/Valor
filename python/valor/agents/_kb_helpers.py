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


def build_correction_section(ticker: str, report_period: str | None, kb_ctx: dict) -> str:
    """Build '## 数据修正提示' section if corrections exist for this ticker/period."""
    if not ticker or not report_period:
        return ""
    try:
        from valor.knowledge_base.corrector import get_corrections
        corrections = get_corrections(ticker, report_period)
    except Exception:
        return ""
    if not corrections:
        return ""
    chunks = kb_ctx.get("chunks") or []
    doc_to_ref = {c.get("doc_id"): f"[C{i+1}]" for i, c in enumerate(chunks)}
    lines = ["## 数据修正提示"]
    lines.append(f"以下字段已根据披露文档修正（ticker={ticker}, period={report_period}）：")
    for c in corrections[:10]:
        ref = doc_to_ref.get(c.source_doc_id, "")
        diff_str = ""
        if c.original_value:
            try:
                old = float(c.original_value)
                new = float(c.corrected_value)
                diff_pct = abs(new - old) / max(abs(old), 1e-9) * 100
                diff_str = f"（原缓存值: {c.original_value}, 差异 {diff_pct:.2f}%）"
            except ValueError:
                diff_str = f"（原缓存值: {c.original_value}）"
        line = (
            f"- {c.field_name}({c.report_period}): {c.corrected_value} {c.unit or ''} "
            f"{ref} {diff_str}"
        ).strip()
        lines.append(line)
    return "\n".join(lines)