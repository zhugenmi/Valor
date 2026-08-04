"""FastAPI routes for knowledge base. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from valor.server import db
from valor.server.envelope import fail, ok

router = APIRouter(prefix="/api/v1", tags=["Knowledge Base"])


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