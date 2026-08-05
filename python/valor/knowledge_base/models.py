"""Pydantic schemas for knowledge base. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class KBDoc(BaseModel):
    doc_id: str
    title: str
    category: Literal["research", "disclosure", "general", "regulatory"]
    sub_type: str
    source: str | None = None
    mime_type: str
    file_path: str
    file_size: int | None = None
    sha256: str
    page_count: int | None = None
    chunk_count: int | None = None
    publish_date: str | None = None
    effective_until: str | None = None
    ticker: str | None = None
    uploaded_at: str
    status: Literal["indexing", "ready", "failed"] = "indexing"
    error_msg: str | None = None
    chunk_strategy: str | None = None
    meta_json: str | None = None


class Chunk(BaseModel):
    chunk_id: str
    doc_id: str
    seq: int
    text: str
    page_no: int | None = None
    heading_path: str | None = None
    token_count: int | None = None
    embed_failed: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None).isoformat())


class Citation(BaseModel):
    chunk_id: str
    doc_id: str
    doc_title: str
    publish_date: str
    vintage: str             # current/recent/legacy/obsolete
    page_no: int | None = None
    cited_text: str


class FinancialFact(BaseModel):
    ticker: str
    report_period: str
    field_name: str
    value: float
    unit: str | None = None
    source_page: int | None = None


class ChunkItem(BaseModel):
    chunk_id: str
    doc_id: str
    seq: int
    text: str
    page_no: int | None = None
    heading_path: str | None = None
    token_count: int | None = None
    embed_failed: bool = False


class DocumentListItem(BaseModel):
    doc_id: str
    title: str
    category: str
    sub_type: str
    mime_type: str
    publish_date: str | None = None
    effective_until: str | None = None
    vintage: str | None = None           # 动态计算
    ticker: str | None = None
    chunk_count: int | None = None
    uploaded_at: str
    status: str


class SearchResultItem(BaseModel):
    query: str
    chunks: list[ChunkItem]
    skipped: bool = False
    reason: str | None = None


class CorrectionItem(BaseModel):
    correction_id: str
    ticker: str
    report_period: str
    field_name: str
    original_value: str | None = None
    corrected_value: str
    unit: str | None = None
    source_doc_id: str
    source_page: int | None = None
    corrected_at: str
    reason: str | None = None


class SubType(BaseModel):
    name: str
    display_name: str


class CategoryInfo(BaseModel):
    category: str
    display_name: str
    sub_types: list[SubType]


class CategoryDict(BaseModel):
    categories: list[CategoryInfo] = [
        CategoryInfo(category="research", display_name="证券研究报告", sub_types=[
            SubType(name="公司研究", display_name="公司研究报告"),
            SubType(name="行业研究", display_name="行业研究报告"),
            SubType(name="宏观经济", display_name="宏观经济报告"),
            SubType(name="投资策略", display_name="投资策略报告"),
        ]),
        CategoryInfo(category="disclosure", display_name="企业融资与披露文档", sub_types=[
            SubType(name="招股说明书", display_name="招股说明书"),
            SubType(name="募集说明书", display_name="募集说明书"),
            SubType(name="annual_report", display_name="年度报告"),
            SubType(name="quarterly_report", display_name="季度报告"),
        ]),
        CategoryInfo(category="general", display_name="金融行业通用文书", sub_types=[
            SubType(name="行政文书", display_name="行政文书"),
            SubType(name="事务文书", display_name="事务文书"),
            SubType(name="经营文书", display_name="经营文书"),
        ]),
        CategoryInfo(category="regulatory", display_name="金融监管与政策文件", sub_types=[
            SubType(name="行业监管规定", display_name="行业监管规定"),
            SubType(name="央行货币政策报告", display_name="央行货币政策报告"),
            SubType(name="政策性文件", display_name="政策性文件"),
        ]),
    ]