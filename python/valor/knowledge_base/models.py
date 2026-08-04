"""Pydantic schemas for knowledge base. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

from datetime import datetime
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
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())