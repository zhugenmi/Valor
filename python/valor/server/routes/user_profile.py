"""User profile routes: memory list (placeholder - no insert endpoint yet).

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from fastapi import APIRouter

from valor.server.db import get_conn
from valor.server.envelope import ok

router = APIRouter(prefix="/api/v1", tags=["UserProfile"])


@router.get("/user/profile")
async def get_profiles():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, content, created_at FROM user_profile ORDER BY id DESC"
        ).fetchall()
    profiles = [{"id": r["id"], "content": r["content"]} for r in rows]
    return ok({"profiles": profiles})


@router.delete("/user/profile/{profile_id}")
async def delete_profile(profile_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM user_profile WHERE id=?", (profile_id,))
    return ok(None)
