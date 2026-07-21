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
    items = []
    for m in msgs:
        event_type = m.event_type or "message"
        # Map persisted ConversationMessage back to SSE-compatible shape
        # so the frontend's processSSEEvent can replay it correctly.
        sse_data: dict = {
            "event": event_type,
            "data": {
                "role": m.role,
                "conversation_id": m.conversation_id,
                "thread_id": m.thread_id or "",
                "task_id": "",
                "item_id": m.id,
                "metadata": {},
                "payload": {"content": m.content or ""},
            },
        }
        # User messages use component_type "markdown" for the chat renderer
        if m.role == "user":
            sse_data["data"]["component_type"] = "markdown"
        items.append(sse_data)
    return {
        "code": 0,
        "data": {
            "conversation_id": conversation_id,
            "items": items,
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
