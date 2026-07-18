"""Models routes: LLM provider config + model availability check.

Integrates with valor.adapters.llm.registry for known providers and
valor.adapters.llm.router for live checks. Persists config to SQLite.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from valor.adapters.llm.protocol import Message
from valor.adapters.llm.registry import list_providers
from valor.adapters.llm.router import get_llm_provider
from valor.server.db import get_conn
from valor.server.envelope import fail, ok

router = APIRouter(prefix="/api/v1", tags=["Models"])


def _known_providers() -> list[str]:
    try:
        return list_providers()
    except Exception:
        return []


@router.get("/models/providers")
async def list_model_providers():
    """Return known providers with is_default + has_api_key flags."""
    known = _known_providers()
    out = []
    with get_conn() as conn:
        for name in known:
            row = conn.execute(
                "SELECT is_default, api_key FROM provider_config WHERE provider=?",
                (name,),
            ).fetchone()
            out.append({
                "provider": name,
                "is_default": bool(row["is_default"]) if row else False,
                "has_api_key": bool(row and row["api_key"]) if row else False,
            })
    return ok(out)


@router.get("/models/providers/{provider}")
async def get_provider_detail(provider: str):
    if provider not in _known_providers():
        return fail(404, "unknown provider")
    with get_conn() as conn:
        cfg = conn.execute(
            "SELECT api_key, base_url, is_default, default_model_id FROM provider_config WHERE provider=?",
            (provider,),
        ).fetchone()
        models = conn.execute(
            "SELECT model_id, model_name FROM provider_model WHERE provider=?",
            (provider,),
        ).fetchall()
    return ok({
        "api_key": cfg["api_key"] if cfg else "",
        "api_key_url": "",
        "base_url": cfg["base_url"] if cfg else "",
        "is_default": bool(cfg["is_default"]) if cfg else False,
        "default_model_id": cfg["default_model_id"] if cfg else "",
        "models": [{"model_id": m["model_id"], "model_name": m["model_name"]} for m in models],
    })


@router.put("/models/providers/{provider}/config")
async def update_provider_config(provider: str, body: dict):
    if provider not in _known_providers():
        return fail(404, "unknown provider")
    api_key = body.get("api_key")
    base_url = body.get("base_url")
    now = datetime.now(UTC).isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO provider_config(provider, api_key, base_url, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(provider) DO UPDATE SET api_key=excluded.api_key, "
            "base_url=excluded.base_url, updated_at=excluded.updated_at",
            (provider, api_key, base_url, now),
        )
    return ok(None)


@router.post("/models/providers/{provider}/models")
async def add_provider_model(provider: str, body: dict):
    if provider not in _known_providers():
        return fail(404, "unknown provider")
    model_id = body.get("model_id")
    model_name = body.get("model_name")
    if not model_id or not model_name:
        return fail(1, "model_id and model_name required")
    now = datetime.now(UTC).isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO provider_model(provider, model_id, model_name, created_at) "
            "VALUES (?, ?, ?, ?)",
            (provider, model_id, model_name, now),
        )
    return ok({"model_id": model_id, "model_name": model_name})


@router.delete("/models/providers/{provider}/models")
async def delete_provider_model(provider: str, model_id: str):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM provider_model WHERE provider=? AND model_id=?",
            (provider, model_id),
        )
    return ok(None)


@router.put("/models/providers/default")
async def set_default_provider(body: dict):
    provider = body.get("provider")
    if not provider or provider not in _known_providers():
        return fail(404, "unknown provider")
    now = datetime.now(UTC).isoformat()
    with get_conn() as conn:
        conn.execute("UPDATE provider_config SET is_default=0")
        conn.execute(
            "UPDATE provider_config SET is_default=1, updated_at=? WHERE provider=?",
            (now, provider),
        )
    return ok(None)


@router.put("/models/providers/{provider}/default-model")
async def set_default_model(provider: str, body: dict):
    if provider not in _known_providers():
        return fail(404, "unknown provider")
    model_id = body.get("model_id", "")
    now = datetime.now(UTC).isoformat()
    with get_conn() as conn:
        conn.execute(
            "UPDATE provider_config SET default_model_id=?, updated_at=? WHERE provider=?",
            (model_id, now, provider),
        )
    return ok(None)


@router.post("/models/check")
async def check_model(body: dict):
    provider = body.get("provider")
    model_id = body.get("model_id", "")
    api_key = body.get("api_key")
    if not provider:
        return fail(1, "provider required")
    if provider not in _known_providers():
        return fail(404, "unknown provider")

    if not api_key:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT api_key FROM provider_config WHERE provider=?",
                (provider,),
            ).fetchone()
            api_key = row["api_key"] if row else None
    if not api_key:
        return ok({"ok": False, "provider": provider, "model_id": model_id,
                   "error": "api_key not configured"})

    try:
        llm = get_llm_provider(provider, api_key=api_key)
        await llm.chat(
            messages=[Message(role="user", content="ping")],
            max_tokens=1,
        )
    except Exception as exc:
        return ok({"ok": False, "provider": provider, "model_id": model_id,
                   "error": str(exc)})
    return ok({"ok": True, "provider": provider, "model_id": model_id,
               "status": "reachable"})
