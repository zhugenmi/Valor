"""Auth routes: placeholder auth that satisfies frontend contract.

No JWT signing or password hashing - /auth/me returns a default local user,
/refresh echoes the incoming token. Matches frontend api-client.ts expectations.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from fastapi import APIRouter

from valor.server.envelope import fail, ok

router = APIRouter(prefix="/api/v1", tags=["Auth"])

_DEFAULT_USER = {
    "id": "local",
    "email": "",
    "name": "本地用户",
    "avatar": "",
    "created_at": "",
    "updated_at": "",
}


@router.get("/auth/me")
async def auth_me():
    """Return default local user (no token validation)."""
    return ok(_DEFAULT_USER)


@router.post("/auth/logout")
async def auth_logout():
    """Clear server-side session placeholder (no-op)."""
    return ok(None)


@router.post("/refresh")
async def refresh(body: dict):
    """Echo refresh token as new access_token (placeholder)."""
    refresh_token = body.get("refreshToken")
    if not refresh_token:
        return fail(1, "missing refreshToken")
    return ok({"access_token": refresh_token, "refresh_token": refresh_token})
