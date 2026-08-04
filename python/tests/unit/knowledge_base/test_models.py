"""Tests for models. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from valor.knowledge_base.models import (
    CategoryDict,
    Citation,
    DocumentListItem,
    FinancialFact,
    SearchResultItem,
)


def test_citation_defaults():
    c = Citation(chunk_id="c1", doc_id="d1", doc_title="t",
                 publish_date="2024-01-01", vintage="current", cited_text="x")
    assert c.page_no is None
    assert c.cited_text == "x"


def test_financial_fact():
    f = FinancialFact(ticker="600519", report_period="2024Q3",
                      field_name="revenue", value=1238.45, unit="亿元", source_page=3)
    assert f.field_name == "revenue"


def test_search_result_item_with_chunks():
    item = SearchResultItem(query="测试", chunks=[], skipped=True, reason="low_relevance")
    assert item.skipped is True


def test_document_list_item_from_doc():
    from datetime import datetime
    from valor.knowledge_base.models import KBDoc
    doc = KBDoc(doc_id="d1", title="t", category="research", sub_type="公司研究",
                mime_type="application/pdf", file_path="x", sha256="abc",
                uploaded_at=datetime.utcnow().isoformat())
    item = DocumentListItem.model_validate(doc.model_dump())
    assert item.doc_id == "d1"


def test_category_dict_has_4_categories():
    d = CategoryDict()
    assert len(d.categories) == 4
    names = {c.category for c in d.categories}
    assert names == {"research", "disclosure", "general", "regulatory"}