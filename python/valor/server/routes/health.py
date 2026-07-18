"""Health check endpoint — used by the frontend's BackendHealthCheck component."""

from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/healthz")
async def healthz() -> bool:
    """Return true when the server is ready to accept requests."""
    return True
