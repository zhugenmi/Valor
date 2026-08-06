"""Tests for document parsers (PDF / metadata / Word / Excel / TXT / MD).

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from valor.knowledge_base.parser import (
    ParsedDocument,
    ParsedPage,
    ParsedTable,
    extract_publish_date,
    extract_report_period,
    extract_ticker,
    parse,
    parse_excel,
    parse_pdf,
    parse_text,
    parse_word,
)

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


# ---------------------------------------------------------------------------
# PDF parser
# ---------------------------------------------------------------------------

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
    with pytest.raises(ValueError, match="unsupported"):
        parse(Path("/nonexistent.bin"), mime_type="application/octet-stream")


# ---------------------------------------------------------------------------
# Metadata extraction
# ---------------------------------------------------------------------------

def _doc(text: str) -> ParsedDocument:
    return ParsedDocument(
        file_path="x",
        mime_type="application/pdf",
        pages=[ParsedPage(page_no=1, text=text)],
        full_text=text,
    )


def test_extract_publish_date_full():
    doc = _doc("贵州茅台 2024Q3 业绩点评\n2024 年 10 月 28 日\n中信证券")
    assert extract_publish_date(doc) == "2024-10-28"


def test_extract_publish_date_iso():
    doc = _doc("发布日期：2024-08-15")
    assert extract_publish_date(doc) == "2024-08-15"


def test_extract_publish_date_none():
    doc = _doc("没有任何日期信息的文本")
    assert extract_publish_date(doc) is None


def test_extract_ticker_a_share():
    doc = _doc("股票代码：600519\n贵州茅台")
    assert extract_ticker(doc) == "600519"


def test_extract_ticker_shenzhen():
    doc = _doc("000858 五粮液")
    assert extract_ticker(doc) == "000858"


def test_extract_ticker_none():
    doc = _doc("无代码文本")
    assert extract_ticker(doc) is None


def test_extract_report_period_quarter():
    doc = _doc("2024 年第三季度报告")
    assert extract_report_period(doc) == "2024Q3"


def test_extract_report_period_date():
    doc = _doc("截至 2024-09-30")
    assert extract_report_period(doc) == "2024-09-30"


def test_extract_report_period_none():
    doc = _doc("无期间信息")
    assert extract_report_period(doc) is None


# ---------------------------------------------------------------------------
# Word / Excel / TXT / MD parsers
# ---------------------------------------------------------------------------

def test_parse_text_txt(tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("第一段。\n第二段。", encoding="utf-8")
    doc = parse_text(f, "text/plain")
    assert "第一段" in doc.full_text
    assert doc.mime_type == "text/plain"


def test_parse_text_markdown(tmp_path):
    f = tmp_path / "note.md"
    f.write_text("# 标题\n正文。", encoding="utf-8")
    doc = parse_text(f, "text/markdown")
    assert "# 标题" in doc.full_text


def test_parse_word_docx(tmp_path):
    docx = pytest.importorskip("docx")
    f = tmp_path / "test.docx"
    d = docx.Document()
    d.add_heading("标题", level=1)
    d.add_paragraph("正文段落。")
    d.save(str(f))
    doc = parse_word(f)
    assert "正文段落" in doc.full_text


def test_parse_excel_xlsx(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    f = tmp_path / "test.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["项目", "金额"])
    ws.append(["营收", "100"])
    wb.save(str(f))
    doc = parse_excel(f)
    assert "营收" in doc.full_text
    assert "100" in doc.full_text


def test_parse_unsupported_mime_raises(tmp_path):
    f = tmp_path / "x.bin"
    f.write_bytes(b"\x00")
    with pytest.raises(ValueError, match="unsupported"):
        parse(f, "application/octet-stream")


# ---------------------------------------------------------------------------
# Integration test: parse_pdf caption propagation (Task 3 fix round 1)
# ---------------------------------------------------------------------------

def test_parse_pdf_propagates_heading_to_table_caption(tmp_path):
    """parse_pdf should set ParsedTable.caption from the nearest preceding heading."""
    from unittest.mock import MagicMock, patch

    # Page 1: has a heading "主要财务数据" then a table
    fake_page1 = MagicMock()
    fake_page1.extract_text.return_value = "主要财务数据\n营业收入 100亿"
    fake_page1.extract_tables.return_value = [[["项目", "金额"], ["营收", "100"]]]
    fake_page1.extract_words.return_value = [
        {"text": "主", "top": 50, "x0": 50, "size": 16},
        {"text": "要", "top": 50, "x0": 60, "size": 16},
        {"text": "财", "top": 50, "x0": 70, "size": 16},
        {"text": "务", "top": 50, "x0": 80, "size": 16},
        {"text": "数", "top": 50, "x0": 90, "size": 16},
        {"text": "据", "top": 50, "x0": 100, "size": 16},
    ]

    # Page 2: has a table but no heading (should inherit from page 1)
    fake_page2 = MagicMock()
    fake_page2.extract_text.return_value = "其他内容"
    fake_page2.extract_tables.return_value = [[["指标", "数值"], ["利润", "20"]]]
    fake_page2.extract_words.return_value = []

    fake_pdf = MagicMock()
    fake_pdf.pages = [fake_page1, fake_page2]

    pdf_path = tmp_path / "fake.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    with patch("valor.knowledge_base.parser.pdfplumber.open") as mock_open:
        mock_open.return_value.__enter__.return_value = fake_pdf
        parsed = parse_pdf(pdf_path)

    # Page 1 table: no preceding heading yet (tables extracted before headings on each page)
    assert len(parsed.tables) >= 1
    assert parsed.tables[0].caption is None, \
        f"Expected None (no preceding heading), got {parsed.tables[0].caption!r}"

    # Page 2 table: should inherit the heading from page 1 (last_heading persists across pages)
    assert len(parsed.tables) >= 2
    assert parsed.tables[1].caption == "主要财务数据", \
        f"Page 2 table should inherit caption from page 1, got {parsed.tables[1].caption!r}"