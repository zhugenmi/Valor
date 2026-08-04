"""FastAPI routes for knowledge base. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from valor.server import db
from valor.server.envelope import fail, ok

from valor.knowledge_base.constants import VINTAGE_RULES, select_strategy
from valor.knowledge_base.indexer import index_document, reindex_document
from valor.knowledge_base.kb_store import (
    delete_document as _delete_doc,
    get_chunks_by_doc,
    get_document,
    insert_document,
    is_sha256_exists,
    list_documents,
    update_document_status,
)
from valor.knowledge_base.models import (
    CategoryDict,
    ChunkItem,
    DocumentListItem,
    KBDoc,
    SearchResultItem,
)
from valor.knowledge_base.parser import (
    extract_publish_date,
    extract_report_period,
    extract_ticker,
    parse,
)
from valor.knowledge_base.retriever import retrieve as _retrieve
from valor.knowledge_base.storage import delete_file, save_upload

router = APIRouter(prefix="/api/v1", tags=["Knowledge Base"])


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _get_files_dir() -> Path:
    base = os.getenv("VALOR_KB_FILES_DIR", "data/kb_files")
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _compute_effective_until(category: str, publish_date: str | None) -> str | None:
    if not publish_date:
        return None
    try:
        pd = datetime.fromisoformat(publish_date)
    except ValueError:
        return None
    months = VINTAGE_RULES.get(category, 12)
    year = pd.year + (pd.month - 1 + months) // 12
    month = (pd.month - 1 + months) % 12 + 1
    try:
        return pd.replace(year=year, month=month).date().isoformat()
    except ValueError:
        return None


def _compute_vintage(doc: KBDoc, now: datetime) -> str:
    meta = json.loads(doc.meta_json) if doc.meta_json else {}
    if meta.get("vintage_override") == "obsolete":
        return "obsolete"
    if not doc.effective_until:
        return "legacy"
    try:
        eu = datetime.fromisoformat(doc.effective_until)
    except ValueError:
        return "legacy"
    days_overdue = (now - eu).days
    if days_overdue <= 0:
        return "current"
    elif days_overdue <= 365:
        return "recent"
    return "legacy"


def _bg_index(doc_id: str, file_path: Path, mime_type: str, strategy, enable_correction: bool) -> None:  # noqa: ANN001
    try:
        parsed = parse(Path(file_path), mime_type)
        index_document(doc_id, parsed, strategy, enable_correction=enable_correction)
    except Exception as exc:
        update_document_status(doc_id, status="failed", error_msg=str(exc), chunk_count=None)


# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------

@router.get("/kb/health")
async def kb_health():
    """Health check for KB subsystem components."""
    embedder_ok = False
    reranker_ok = False
    try:
        from valor.knowledge_base.embedder import get_embedder
        get_embedder()  # 触发懒加载
        embedder_ok = True
    except Exception:
        pass
    try:
        from valor.knowledge_base.retriever import get_reranker
        get_reranker()
        reranker_ok = True
    except Exception:
        pass

    data = {
        "sqlite_vec": "ok" if db.KB_AVAILABLE else "unavailable",
        "fts5": "ok",
        "embedder": "ok" if embedder_ok else "unavailable",
        "reranker": "ok" if reranker_ok else "unavailable",
    }
    # 若 sqlite-vec 不可用，返回 503
    if not db.KB_AVAILABLE:
        return JSONResponse(status_code=503, content=fail(503, "sqlite-vec unavailable", data))
    return ok(data)


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------

@router.post("/kb/documents")
async def upload_document(
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    category: str = Form(...),
    sub_type: str = Form(...),
    publish_date: str = Form(None),
    enable_correction: bool = Form(True),
    file: UploadFile = File(...),
):
    doc_id = str(uuid.uuid4())
    sha, size, file_path = await save_upload(file, doc_id, _get_files_dir())
    # Dedup
    existing = is_sha256_exists(sha)
    if existing and existing != doc_id:
        delete_file(file_path)
        return fail(409, f"document with same sha256 already exists: {existing}")

    # Parse synchronously to extract metadata
    try:
        parsed = parse(file_path, file.content_type or "application/octet-stream")
    except ValueError as exc:
        delete_file(file_path)
        return fail(415, str(exc))
    except Exception as exc:
        delete_file(file_path)
        return fail(422, f"parse failed: {exc}")

    # Extract metadata
    if not publish_date:
        publish_date = extract_publish_date(parsed)
    effective_until = _compute_effective_until(category, publish_date)
    ticker = extract_ticker(parsed)
    report_period = extract_report_period(parsed) if category == "disclosure" else None

    # Persist document row
    now = datetime.utcnow().isoformat()
    meta = {"report_period": report_period, "enable_correction": enable_correction}
    doc = KBDoc(
        doc_id=doc_id, title=title, category=category, sub_type=sub_type,
        source="用户上传", mime_type=file.content_type or "application/octet-stream",
        file_path=str(file_path), file_size=size, sha256=sha,
        page_count=len(parsed.pages), publish_date=publish_date,
        effective_until=effective_until, ticker=ticker,
        uploaded_at=now, status="indexing", chunk_strategy=select_strategy(category, sub_type).name,
        meta_json=json.dumps(meta, ensure_ascii=False),
    )
    insert_document(doc)

    # Background index
    strategy = select_strategy(category, sub_type)
    background_tasks.add_task(
        _bg_index, doc_id, file_path, file.content_type or "application/octet-stream",
        strategy, enable_correction,
    )

    return ok({"doc_id": doc_id, "status": "indexing"})


@router.get("/kb/documents")
async def list_docs(
    category: str = None, sub_type: str = None, ticker: str = None,
    limit: int = 50, offset: int = 0,
):
    items, total = list_documents(category, sub_type, ticker, limit, offset)
    now = datetime.utcnow()
    out = []
    for doc in items:
        item = DocumentListItem.model_validate(doc.model_dump())
        item.vintage = _compute_vintage(doc, now)
        out.append(item)
    return ok({"items": [i.model_dump() for i in out], "total": total})


@router.get("/kb/documents/{doc_id}")
async def get_doc_detail(doc_id: str):
    doc = get_document(doc_id)
    if doc is None:
        return fail(404, "document not found")
    item = DocumentListItem.model_validate(doc.model_dump())
    item.vintage = _compute_vintage(doc, datetime.utcnow())
    return ok(item.model_dump())


@router.get("/kb/documents/{doc_id}/file")
async def get_doc_file(doc_id: str):
    doc = get_document(doc_id)
    if doc is None:
        return fail(404, "document not found")
    p = Path(doc.file_path)
    if not p.exists():
        return fail(404, "file not found on disk")
    return FileResponse(p, media_type=doc.mime_type, filename=p.name)


@router.get("/kb/documents/{doc_id}/chunks")
async def get_doc_chunks(doc_id: str):
    doc = get_document(doc_id)
    if doc is None:
        return fail(404, "document not found")
    chunks = get_chunks_by_doc(doc_id)
    items = [ChunkItem.model_validate(c.model_dump()) for c in chunks]
    return ok([i.model_dump() for i in items])


@router.delete("/kb/documents/{doc_id}")
async def delete_doc(doc_id: str):
    doc = get_document(doc_id)
    if doc is None:
        return fail(404, "document not found")
    _delete_doc(doc_id)
    delete_file(Path(doc.file_path))
    return ok({"doc_id": doc_id, "deleted": True})


@router.post("/kb/documents/{doc_id}/reindex")
async def reindex_doc(doc_id: str, strategy_name: str = None):
    doc = get_document(doc_id)
    if doc is None:
        return fail(404, "document not found")
    update_document_status(doc_id, status="indexing", error_msg=None, chunk_count=None)
    count = reindex_document(doc_id, strategy_name)
    return ok({"doc_id": doc_id, "chunk_count": count, "status": "ready"})


@router.get("/kb/categories")
async def get_categories():
    return ok(CategoryDict().model_dump())


@router.post("/kb/search")
async def kb_search(body: dict):
    """Manual retrieval endpoint for debugging / frontend 试检索."""
    query = body.get("query", "")
    top_k = body.get("top_k", 5)
    vintage_filter = body.get("vintage_filter")
    if not query:
        return fail(400, "query is required")
    results = _retrieve(query, top_k=top_k, vintage_filter=vintage_filter)
    chunks = [
        ChunkItem(
            chunk_id=r.chunk_id, doc_id=r.doc_id, seq=0, text=r.text,
            page_no=r.page_no, heading_path=r.heading_path,
            token_count=len(r.text),
        ) for r in results
    ]
    item = SearchResultItem(query=query, chunks=chunks)
    return ok(item.model_dump())