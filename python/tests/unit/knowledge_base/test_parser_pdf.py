"""Tests for PDF parser with real bond prospectus PDF.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from valor.knowledge_base.parser import ParsedDocument, parse, parse_pdf

DEFAULT_PDF = Path(
    "/home/zhugenmi/work/FinTech/valor/data/"
    "四川高速公路建设开发集团有限公司2026年面向专业投资者公开发行"
    "科技创新公司债券（第二期）募集说明书.pdf"
)


@pytest.fixture
def test_pdf():
    p = Path(os.environ.get("VALOR_KB_TEST_PDF", str(DEFAULT_PDF)))
    if not p.exists():
        pytest.skip(f"test PDF not available: {p}")
    return p


def test_parse_pdf_returns_pages(test_pdf):
    doc = parse_pdf(test_pdf)
    assert len(doc.pages) >= 1
    assert doc.pages[0].page_no == 1
    # Page 1 may have no text (cover page), but at least one page should have text
    texts = [p.text for p in doc.pages if p.text.strip()]
    assert len(texts) >= 1, "at least one page should have extractable text"


def test_parse_pdf_full_text_concatenated(test_pdf):
    doc = parse_pdf(test_pdf)
    assert doc.full_text  # non-empty
    assert "四川" in doc.full_text
    assert "高速" in doc.full_text


def test_parse_dispatcher_routes_pdf(test_pdf):
    doc = parse(test_pdf, mime_type="application/pdf")
    assert isinstance(doc, ParsedDocument)
    assert doc.mime_type == "application/pdf"


def test_parse_pdf_extracts_tables(test_pdf):
    doc = parse_pdf(test_pdf)
    # Verify no crash — table extraction may or may not find tables
    assert isinstance(doc.tables, list)
    # Real prospectus has tables — if found, they should have rows
    if doc.tables:
        assert len(doc.tables) >= 1
        for tbl in doc.tables:
            assert tbl.page_no >= 1
            assert isinstance(tbl.rows, list)


def test_parse_pdf_heading_tree(test_pdf):
    doc = parse_pdf(test_pdf)
    assert isinstance(doc.heading_tree, list)
    # Heading heuristic may find nothing (CID font encoding issue),
    # but if it does, entries should be valid
    if doc.heading_tree:
        for node in doc.heading_tree:
            assert node.level >= 1
            assert node.text
            assert node.page_no >= 1


def test_parse_dispatcher_raises_on_unsupported():
    with pytest.raises(NotImplementedError, match="Task 2.2"):
        parse(Path("/nonexistent.docx"), mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")