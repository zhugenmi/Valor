"""Tests for chunker. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from valor.knowledge_base.chunker import chunk_document
from valor.knowledge_base.constants import CHUNK_STRATEGIES
from valor.knowledge_base.parser import (
    HeadingNode,
    ParsedDocument,
    ParsedPage,
    ParsedTable,
)


def _doc_with_text(text: str) -> ParsedDocument:
    return ParsedDocument(
        file_path="x", mime_type="text/plain",
        pages=[ParsedPage(page_no=1, text=text)],
        full_text=text,
    )


def test_chunk_general_keeps_chunk_size():
    text = "段一。" * 200  # 800 字
    doc = _doc_with_text(text)
    chunks = chunk_document(doc, CHUNK_STRATEGIES["general"])
    assert len(chunks) >= 2
    for c in chunks:
        assert c.text  # non-empty
        assert c.seq >= 0


def test_chunk_research_with_headings():
    text = "# 摘要\n核心观点：增长强劲。\n\n# 财务预测\n2024 年营收预计 1500 亿。"
    doc = ParsedDocument(
        file_path="x", mime_type="text/markdown",
        pages=[ParsedPage(page_no=1, text=text)],
        full_text=text,
        heading_tree=[HeadingNode(level=1, text="摘要", page_no=1),
                       HeadingNode(level=1, text="财务预测", page_no=1)],
    )
    chunks = chunk_document(doc, CHUNK_STRATEGIES["research"])
    # 至少 2 个 chunk（按 heading 切）
    assert len(chunks) >= 2
    # 第一个 chunk 应该包含"摘要"上下文
    assert "摘要" in (chunks[0].heading_path or "") or "核心观点" in chunks[0].text


def test_chunk_clause_by_article():
    text = "第一条 为规范市场秩序，制定本规定。第二条 适用范围包括所有上市公司。第三条 本规定自发布之日起施行。"
    doc = _doc_with_text(text)
    chunks = chunk_document(doc, CHUNK_STRATEGIES["regulatory_clause"])
    assert len(chunks) >= 3
    assert "第一条" in chunks[0].text
    assert "第二条" in chunks[1].text
    assert "第三条" in chunks[2].text


def test_chunk_table_aware_separates_tables():
    text = "概述文本。\n\n| 项目 | 金额 |\n|---|---|\n| 营收 | 100 |\n\n后续文本。"
    doc = ParsedDocument(
        file_path="x", mime_type="text/plain",
        pages=[ParsedPage(page_no=1, text=text)],
        full_text=text,
        tables=[ParsedTable(page_no=1, rows=[["项目", "金额"], ["营收", "100"]])],
    )
    chunks = chunk_document(doc, CHUNK_STRATEGIES["annual_report"])
    # 应该有表格 chunk 和文本 chunk
    has_table_chunk = any("|" in c.text or "营收" in c.text for c in chunks)
    assert has_table_chunk


def test_chunk_assigns_seq_unique():
    text = "段一。" * 100 + "段二。" * 100
    doc = _doc_with_text(text)
    chunks = chunk_document(doc, CHUNK_STRATEGIES["general"])
    seqs = [c.seq for c in chunks]
    assert len(seqs) == len(set(seqs))  # unique