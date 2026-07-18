"""Tasks routes: cancel placeholder (no real scheduler yet).

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from fastapi import APIRouter

from valor.server.envelope import ok

router = APIRouter(prefix="/api/v1", tags=["Tasks"])


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    """Placeholder cancel - always succeeds (no scheduler backend)."""
    return ok(None)
