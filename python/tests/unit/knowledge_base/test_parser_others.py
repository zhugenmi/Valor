"""Tests for Word/Excel/TXT/MD parsers.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
import pytest

from valor.knowledge_base.parser import parse, parse_excel, parse_text, parse_word


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