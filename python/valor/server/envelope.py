"""ApiResponse envelope helpers - unify all route return shapes.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Standard envelope: {code, data, msg}."""

    code: int = 0
    data: T | None = None
    msg: str = "ok"


def ok(data: object = None, msg: str = "ok") -> dict:
    """Success envelope."""
    return {"code": 0, "data": data, "msg": msg}


def fail(code: int, msg: str, data: object = None) -> dict:
    """Failure envelope (HTTP still 200)."""
    return {"code": code, "data": data, "msg": msg}


__all__ = ["ApiResponse", "ok", "fail"]
