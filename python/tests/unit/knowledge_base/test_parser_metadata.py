"""Tests for metadata extraction. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from valor.knowledge_base.parser import (
    ParsedDocument,
    ParsedPage,
    extract_publish_date,
    extract_report_period,
    extract_ticker,
)


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