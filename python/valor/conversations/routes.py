"""REST API routes for conversations. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

from fastapi import APIRouter

from valor.conversations.storage import (
    delete_conversation as _delete_conversation,
    get_messages,
    list_conversations,
)

router = APIRouter(prefix="/api/v1", tags=["Conversations"])


@router.get("/conversations/")
async def list_conversations_route():
    items = list_conversations()
    return {
        "code": 0,
        "data": {
            "conversations": [c.model_dump() for c in items],
            "total": len(items),
        },
        "msg": "ok",
    }


@router.get("/conversations/{conversation_id}/history")
async def conversation_history_route(conversation_id: str):
    msgs = get_messages(conversation_id)
    return {
        "code": 0,
        "data": {
            "conversation_id": conversation_id,
            "items": [m.model_dump() for m in msgs],
        },
        "msg": "ok",
    }


@router.delete("/conversations/{conversation_id}")
async def delete_conversation_route(conversation_id: str):
    _delete_conversation(conversation_id)
    return {"code": 0, "data": None, "msg": "ok"}


# Stub retained for frontend compatibility
@router.get("/conversations/{conversation_id}/scheduled-task-results")
async def conversation_scheduled_results_route(conversation_id: str):
    return {
        "code": 0,
        "data": {"conversation_id": conversation_id, "items": []},
        "msg": "ok",
    }


@router.get("/conversations/scheduled-task-results")
async def all_scheduled_results_route():
    return {"code": 0, "data": {"agents": []}, "msg": "ok"}


__all__ = ["router"]
