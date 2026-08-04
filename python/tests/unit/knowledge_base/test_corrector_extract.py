"""Tests for financial fact extraction. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from valor.knowledge_base.corrector import extract_financial_facts
from valor.knowledge_base.parser import ParsedDocument, ParsedPage, ParsedTable


def test_extract_revenue_from_table():
    doc = ParsedDocument(
        file_path="x", mime_type="application/pdf",
        pages=[ParsedPage(page_no=1, text="主要会计数据")],
        full_text="主要会计数据",
        tables=[ParsedTable(page_no=1, rows=[
            ["项目", "本期金额", "上期金额"],
            ["营业收入", "1,238.45", "1,075.34"],
            ["归属于上市公司股东的净利润", "608.45", "527.86"],
        ])],
    )
    facts = extract_financial_facts(doc, ticker="600519", report_period="2024Q3")
    assert any(f.field_name == "revenue" and abs(f.value - 1238.45) < 0.01 for f in facts)
    assert any(f.field_name == "net_profit" and abs(f.value - 608.45) < 0.01 for f in facts)


def test_extract_handles_unit_yi():
    """Table caption mentions 亿元."""
    doc = ParsedDocument(
        file_path="x", mime_type="application/pdf",
        pages=[ParsedPage(page_no=1, text="单位：亿元")],
        full_text="单位：亿元",
        tables=[ParsedTable(page_no=1, caption="单位：亿元", rows=[
            ["项目", "金额"],
            ["营业收入", "1238.45"],
        ])],
    )
    facts = extract_financial_facts(doc, "600519", "2024Q3")
    assert any(f.field_name == "revenue" for f in facts)
    assert facts[0].unit == "亿元"


def test_extract_skips_unmapped_rows():
    doc = ParsedDocument(
        file_path="x", mime_type="application/pdf",
        pages=[],
        full_text="",
        tables=[ParsedTable(page_no=1, rows=[
            ["项目", "金额"],
            ["未知字段", "100"],
            ["营业收入", "200"],
        ])],
    )
    facts = extract_financial_facts(doc, "600519", "2024Q3")
    assert all(f.field_name != "未知字段" for f in facts)
    assert any(f.field_name == "revenue" for f in facts)


def test_extract_parses_numbers_with_commas():
    doc = ParsedDocument(
        file_path="x", mime_type="application/pdf",
        pages=[],
        full_text="",
        tables=[ParsedTable(page_no=1, rows=[
            ["项目", "金额"],
            ["基本每股收益", "1.23"],
        ])],
    )
    facts = extract_financial_facts(doc, "600519", "2024Q3")
    assert any(f.field_name == "eps" and abs(f.value - 1.23) < 0.001 for f in facts)
