"""SSE streaming endpoint for agent analysis.

Receives a POST request with { query, agent_name, conversation_id, start_date?, end_date? }
and streams back SSE events (conversation_started → reasoning → message → done).

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

import asyncio
import json
import logging
import math
import uuid
from datetime import UTC, datetime
from typing import AsyncGenerator

from fastapi import APIRouter
from starlette.responses import StreamingResponse

from valor.agents.workflow import stream_analysis
from valor.conversations.models import Conversation, ConversationMessage
from valor.conversations.storage import (
    append_message,
    create_conversation,
    update_conversation_status,
)
from valor.portfolio.storage import PortfolioNotFound
from valor.server.data_preflight import ensure_latest_trading_day_data
from valor.server.intent import classify_intent
from valor.server.portfolio_context import load_portfolio_context

router = APIRouter(prefix="/api/v1", tags=["Stream"])

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_nan(obj: object) -> object:
    """Recursively replace NaN/Infinity with None for valid JSON output."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean_nan(v) for v in obj]
    return obj


def _serialize_message(msg: object) -> object:
    """Convert a LangChain BaseMessage to a JSON-serializable dict.

    LangChain messages are Pydantic models that aren't JSON-serializable by
    default; without this, json.dumps(default=str) would render them as
    "content='...' additional_kwargs={} ..." which the frontend can't parse.
    """
    content = getattr(msg, "content", None)
    if content is None and not hasattr(msg, "content"):
        return msg
    return {
        "type": msg.__class__.__name__,
        "content": content,
        "name": getattr(msg, "name", None) or "",
    }


def _serialize_state(obj: object) -> object:
    """Recursively convert state so LangChain messages become plain dicts.

    Descends into dicts and lists; leaves other primitives untouched.
    """
    if isinstance(obj, dict):
        result = {k: _serialize_state(v) for k, v in obj.items()}
        if isinstance(result.get("messages"), list):
            result["messages"] = [_serialize_message(m) for m in result["messages"]]
        return result
    if isinstance(obj, list):
        return [_serialize_state(x) for x in obj]
    return obj


def _json_default(obj: object) -> object:
    """Fallback JSON encoder for non-standard types (Timestamp, numpy, etc.)."""
    # pandas Timestamp / datetime / date
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    # numpy scalar (int64, float64, etc.)
    if hasattr(obj, "item"):
        try:
            return obj.item()
        except (ValueError, AttributeError):
            pass
    # pandas Series / DataFrame
    if hasattr(obj, "to_dict"):
        try:
            return obj.to_dict()
        except Exception:
            pass
    if hasattr(obj, "tolist"):
        try:
            return obj.tolist()
        except Exception:
            pass
    # LangChain message (safety net; _serialize_state should have handled it)
    if hasattr(obj, "content") and hasattr(obj, "name"):
        return _serialize_message(obj)
    return str(obj)


def _sse(event: str, data: object) -> str:
    """Format one SSE message (NaN-safe, message-serializing)."""
    payload = _clean_nan(_serialize_state({"event": event, "data": data}))
    return f"data: {json.dumps(payload, ensure_ascii=False, default=_json_default)}\n\n"


AGENT_ORDER: list[str] = [
    "market_data",
    "technicals",
    "fundamentals",
    "valuation",
    "capital_sentiment",
    "macro_industry",
    "bull_bear_debate",
    "risk_manager",
    "portfolio_manager",
]


def _merge_state(accumulated: dict, delta: dict) -> None:
    """Merge a LangGraph stream chunk into the accumulated state (mutates accumulated).

    Mirrors GraphState reducers: messages use list concat (operator.add),
    data and metadata use dict shallow-merge (last-wins for top-level keys).
    """
    for node_name, node_delta in delta.items():
        for key, value in node_delta.items():
            if key == "messages":
                accumulated.setdefault("messages", []).extend(value)
            else:
                merged_dict = accumulated.setdefault(key, {})
                if isinstance(value, dict) and isinstance(merged_dict, dict):
                    merged_dict.update(value)
                else:
                    accumulated[key] = value


def _extract_final_decision(state: dict) -> dict | None:
    """Extract the portfolio_management_agent's final message as a dict.

    Reverse-iteres state["messages"] to find the last message with
    name == "portfolio_management_agent" and json.loads its content.
    Returns None if not found or content is not valid JSON.

    Attaches `current_position` from state["data"]["portfolio"]["stock"] so the
    frontend can distinguish 持有 (maintain existing position) from 观望 (no
    position, wait-and-see) when action == "hold".
    """
    for msg in reversed(state.get("messages", [])):
        if getattr(msg, "name", None) == "portfolio_management_agent":
            try:
                decision = json.loads(msg.content)
            except (json.JSONDecodeError, TypeError, AttributeError):
                return None
            if isinstance(decision, dict):
                portfolio = state.get("data", {}).get("portfolio", {}) or {}
                if isinstance(portfolio, dict):
                    decision["current_position"] = portfolio.get("stock", 0)
            return decision
    return None


BULL_BEAR_DEBATE_SUB_MESSAGES = ["bull_case_agent", "bear_case_agent", "bull_bear_debate_agent"]
BULL_BEAR_DEBATE_SUB_KEYS = ["bull", "bear", "verdict"]


def _emit_bull_bear_debate_sub_events(
    state_delta: dict, conversation_id: str, thread_id: str,
    skip_keys: set[str] | None = None,
) -> list[str]:
    """If state_delta is from bull_bear_debate node, emit 3 sub-agent_completed events.

    Returns a list of SSE strings (possibly empty if no sub-messages found).
    Each sub-event uses a dot-namespaced agent name like 'bull_bear_debate.bull'.

    Args:
        skip_keys: Sub-keys already streamed via stage_callback. These are not
            re-emitted (and not failed either) since the frontend already has them.
    """
    skip_keys = skip_keys or set()
    sse_events: list[str] = []
    new_messages = state_delta.get("messages", [])
    emitted_keys: set[str] = set()
    for msg in new_messages:
        msg_name = getattr(msg, "name", None)
        if msg_name not in BULL_BEAR_DEBATE_SUB_MESSAGES:
            continue
        sub_key = BULL_BEAR_DEBATE_SUB_KEYS[BULL_BEAR_DEBATE_SUB_MESSAGES.index(msg_name)]
        # Mark as seen even if skipped, so we don't emit agent_failed for it
        emitted_keys.add(sub_key)
        if sub_key in skip_keys:
            continue
        try:
            sub_state = json.loads(msg.content)
        except (json.JSONDecodeError, TypeError):
            sub_state = {"raw": str(getattr(msg, "content", ""))}
        sse_events.append(_sse("agent_completed", {
            "conversation_id": conversation_id,
            "thread_id": thread_id,
            "agent": f"bull_bear_debate.{sub_key}",
            "state": sub_state,
        }))
    # Emit agent_failed for any missing sub-keys so the frontend doesn't stay stuck
    for sub_key in BULL_BEAR_DEBATE_SUB_KEYS:
        if sub_key not in emitted_keys and sub_key not in skip_keys:
            sse_events.append(_sse("agent_failed", {
                "conversation_id": conversation_id,
                "thread_id": thread_id,
                "agent": f"bull_bear_debate.{sub_key}",
                "error": f"Missing {sub_key} stage output",
            }))
    return sse_events


# ---------------------------------------------------------------------------
# SSE endpoint
# ---------------------------------------------------------------------------


@router.post("/agents/stream")
async def agent_stream(body: dict):
    """POST /api/v1/agents/stream — SSE streaming agent analysis."""
    query: str = body.get("query", "")
    agent_name: str = body.get("agent_name", "ValorAgent")
    conversation_id: str = body.get("conversation_id") or str(uuid.uuid4())
    thread_id: str = str(uuid.uuid4())
    start_date: str | None = body.get("start_date") or None
    end_date: str | None = body.get("end_date") or None
    portfolio_id: str | None = body.get("portfolio_id") or None
    request_ticker: str | None = body.get("ticker") or None

    async def _stream() -> AsyncGenerator[str, None]:
        # 1. conversation_started
        yield _sse("conversation_started", {"conversation_id": conversation_id})

        # Persist conversation
        now_iso = datetime.now(UTC).isoformat()
        create_conversation(Conversation(
            id=conversation_id,
            agent_name=agent_name,
            title=query[:30] if query else None,
            status="active",
            portfolio_id=portfolio_id,
            ticker=request_ticker,
            created_at=now_iso,
            updated_at=now_iso,
        ))
        # User message
        _msg_seq = 0

        def _persist(role: str, event_type: str, content: str, msg_id: str | None = None) -> None:
            nonlocal _msg_seq
            _msg_seq += 1
            append_message(ConversationMessage(
                id=msg_id or f"msg-{uuid.uuid4()}",
                conversation_id=conversation_id,
                thread_id=thread_id,
                role=role,
                event_type=event_type,
                content=content,
                created_at=datetime.now(UTC).isoformat(),
                seq=_msg_seq,
            ))

        # 2. Echo the user's message so it renders in the chat UI.
        #    Must come before thread_started: both use item_id="" and "message"
        #    is an append event, so emitting user-first puts it at items[0]
        #    while the agent reply later appends to the empty thread_started
        #    item at items[1].
        #    Use the same id for SSE and DB so the frontend can dedupe by item_id
        #    when replaying history (otherwise SSE user-xxx and DB msg-yyy would
        #    render as two separate messages).
        user_msg_id = f"msg-{uuid.uuid4()}"
        yield _sse("message", {
            "role": "user",
            "conversation_id": conversation_id,
            "thread_id": thread_id,
            "task_id": "",
            "item_id": user_msg_id,
            "metadata": {},
            "payload": {"content": query},
        })
        _persist("user", "message", query, msg_id=user_msg_id)

        # 3. thread_started
        yield _sse("thread_started", {
            "role": "agent",
            "conversation_id": conversation_id,
            "thread_id": thread_id,
            "task_id": "",
            "item_id": "",
            "metadata": {},
            "payload": {"content": ""},
        })

        # Only ValorAgent supports the LangGraph workflow for now
        if agent_name != "ValorAgent":
            reply = f"Agent '{agent_name}' is not yet implemented."
            yield _sse("message", {
                "role": "agent",
                "conversation_id": conversation_id,
                "thread_id": thread_id,
                "task_id": "",
                "item_id": "",
                "metadata": {},
                "payload": {"content": reply},
            })
            _persist("assistant", "message", reply)
            yield _sse("done", {"conversation_id": conversation_id, "thread_id": thread_id})
            return

        # Classify intent: chat / full_analysis / single_analysis
        intent = await classify_intent(query)

        # Chat: reply without running any workflow
        if intent.intent == "chat":
            reply = intent.reply or "您好，请提供股票代码以进行分析。"
            yield _sse("message", {
                "role": "agent",
                "conversation_id": conversation_id,
                "thread_id": thread_id,
                "task_id": "",
                "item_id": "",
                "metadata": {},
                "payload": {"content": reply},
            })
            _persist("assistant", "message", reply)
            yield _sse("done", {"conversation_id": conversation_id, "thread_id": thread_id})
            return

        ticker = intent.ticker
        if not ticker:
            reply = "无法识别股票代码，请提供6位A股代码（如600519）。"
            yield _sse("message", {
                "role": "agent",
                "conversation_id": conversation_id,
                "thread_id": thread_id,
                "task_id": "",
                "item_id": "",
                "metadata": {},
                "payload": {"content": reply},
            })
            _persist("assistant", "message", reply)
            yield _sse("done", {"conversation_id": conversation_id, "thread_id": thread_id})
            return

        # 3. reasoning_started
        yield _sse("reasoning_started", {
            "conversation_id": conversation_id,
            "thread_id": thread_id,
            "task_id": "",
            "item_id": "",
        })

        try:
            # Run the synchronous workflow in a thread pool so the stream stays alive
            from valor.agents.workflow import (
                agent_message_name,
                run_agents,
            )

            loop = asyncio.get_event_loop()
            if intent.intent == "single_analysis":
                target_name = agent_message_name(intent.agent)
                result = await loop.run_in_executor(
                    None,
                    lambda: run_agents(
                        ticker=ticker,
                        agent_names=[intent.agent],
                        start_date=start_date,
                        end_date=end_date,
                    ),
                )

                # Extract the target agent's final message
                final_message = None
                for msg in reversed(result.get("messages", [])):
                    if hasattr(msg, "name") and msg.name == target_name:
                        final_message = msg
                        break

                if final_message:
                    try:
                        content = json.loads(final_message.content)
                        payload = json.dumps(
                            {"ticker": ticker, "decision": content},
                            ensure_ascii=False,
                        )
                        yield _sse("component_generator", {
                            "role": "agent",
                            "conversation_id": conversation_id,
                            "thread_id": thread_id,
                            "task_id": "",
                            "item_id": "",
                            "metadata": {},
                            "payload": {
                                "component_type": "markdown",
                                "content": payload,
                            },
                        })
                    except (json.JSONDecodeError, TypeError):
                        yield _sse("message", {
                            "role": "agent",
                            "conversation_id": conversation_id,
                            "thread_id": thread_id,
                            "task_id": "",
                            "item_id": "",
                            "metadata": {},
                            "payload": {"content": str(final_message.content)},
                        })
                else:
                    # Dump all agent outputs as markdown
                    lines = []
                    for msg in result.get("messages", []):
                        name = getattr(msg, "name", "unknown")
                        try:
                            lines.append(f"**{name}**: {json.dumps(json.loads(msg.content), ensure_ascii=False, indent=2)}")
                        except Exception:
                            lines.append(f"**{name}**: {msg.content}")
                    yield _sse("component_generator", {
                        "role": "agent",
                        "conversation_id": conversation_id,
                        "thread_id": thread_id,
                        "task_id": "",
                        "item_id": "",
                        "metadata": {},
                        "payload": {
                            "component_type": "markdown",
                            "content": "\n\n".join(lines),
                        },
                    })
            else:  # full_analysis - new streaming path
                # Resolve portfolio context (real holdings if portfolio_id provided)
                if portfolio_id and request_ticker:
                    try:
                        portfolio = load_portfolio_context(portfolio_id, request_ticker)
                    except PortfolioNotFound:
                        yield _sse("system_failed", {
                            "role": "system",
                            "conversation_id": conversation_id,
                            "thread_id": thread_id,
                            "task_id": "",
                            "item_id": "",
                            "metadata": {},
                            "payload": {"content": f"组合不存在: {portfolio_id}"},
                        })
                        _persist("system", "system_failed",
                                 json.dumps({"error": f"组合不存在: {portfolio_id}"},
                                            ensure_ascii=False))
                        update_conversation_status(conversation_id, "failed")
                        yield _sse("done", {"conversation_id": conversation_id, "thread_id": thread_id})
                        return
                else:
                    portfolio = {"cash": 100000.0, "stock": 0}

                # Pre-flight: ensure latest trading day data cached
                preflight = ensure_latest_trading_day_data(ticker)
                yield _sse("data_preflight", {
                    "conversation_id": conversation_id,
                    "thread_id": thread_id,
                    "trading_day": preflight["trading_day"],
                    "filled": preflight["filled"],
                })
                _persist("system", "data_preflight", json.dumps(preflight, ensure_ascii=False))

                yield _sse("workflow_started", {
                    "conversation_id": conversation_id,
                    "thread_id": thread_id,
                    "ticker": ticker,
                    "agents": AGENT_ORDER,
                })

                queue: asyncio.Queue = asyncio.Queue()
                # Sub-keys already streamed via stage_callback. Tracked so the
                # final bull_bear_debate node chunk doesn't re-emit them.
                seen_debate_subs: set[str] = set()
                # Capture the running loop so the worker thread can put items
                # into the queue in a thread-safe manner. asyncio.Queue is not
                # thread-safe by itself; put_nowait from another thread may not
                # wake up the event loop's selector.
                running_loop = asyncio.get_running_loop()

                def _put(item) -> None:
                    running_loop.call_soon_threadsafe(queue.put_nowait, item)

                def _stage_callback(sub_key: str, payload: dict) -> None:
                    _put(("debate_stage", (sub_key, payload)))

                def _run_stream_in_thread():
                    try:
                        for chunk in stream_analysis(
                            ticker=ticker,
                            start_date=start_date,
                            end_date=end_date,
                            portfolio=portfolio,
                            stage_callback=_stage_callback,
                        ):
                            _put(("chunk", chunk))
                        _put(("done", None))
                    except Exception as exc:
                        logger.exception("stream_analysis failed")
                        _put(("error", str(exc)))

                loop.run_in_executor(None, _run_stream_in_thread)

                accumulated_state: dict = {}
                while True:
                    event_type, payload = await queue.get()
                    if event_type == "chunk":
                        node_name = next(iter(payload.keys()))
                        state_delta = payload[node_name]
                        _merge_state(accumulated_state, payload)
                        if node_name == "bull_bear_debate":
                            # Emit only sub-events not already streamed via stage_callback
                            for sse_str in _emit_bull_bear_debate_sub_events(
                                state_delta, conversation_id, thread_id,
                                skip_keys=seen_debate_subs,
                            ):
                                yield sse_str
                            _persist("assistant", "agent_completed",
                                     json.dumps({"agent": node_name, "state": state_delta},
                                                default=_json_default, ensure_ascii=False))
                        else:
                            yield _sse("agent_completed", {
                                "conversation_id": conversation_id,
                                "thread_id": thread_id,
                                "agent": node_name,
                                "state": state_delta,
                            })
                            _persist("assistant", "agent_completed",
                                     json.dumps({"agent": node_name, "state": state_delta},
                                                default=_json_default, ensure_ascii=False))
                    elif event_type == "debate_stage":
                        sub_key, sub_payload = payload
                        seen_debate_subs.add(sub_key)
                        yield _sse("agent_completed", {
                            "conversation_id": conversation_id,
                            "thread_id": thread_id,
                            "agent": f"bull_bear_debate.{sub_key}",
                            "state": sub_payload,
                        })
                        _persist("assistant", "agent_completed",
                                 json.dumps({"agent": f"bull_bear_debate.{sub_key}", "state": sub_payload},
                                            default=_json_default, ensure_ascii=False))
                    elif event_type == "done":
                        break
                    elif event_type == "error":
                        yield _sse("system_failed", {
                            "role": "system",
                            "conversation_id": conversation_id,
                            "thread_id": thread_id,
                            "task_id": "",
                            "item_id": "",
                            "metadata": {},
                            "payload": {"content": f"分析失败: {payload}"},
                        })
                        _persist("system", "system_failed", json.dumps({"error": payload}, ensure_ascii=False))
                        update_conversation_status(conversation_id, "failed")
                        yield _sse("done", {"conversation_id": conversation_id, "thread_id": thread_id})
                        return

                final_decision = _extract_final_decision(accumulated_state)
                yield _sse("workflow_completed", {
                    "conversation_id": conversation_id,
                    "thread_id": thread_id,
                    "final_decision": final_decision,
                })
                _persist("assistant", "workflow_completed",
                         json.dumps({"final_decision": final_decision},
                                    default=_json_default, ensure_ascii=False))
                update_conversation_status(conversation_id, "completed")

        except Exception as exc:
            yield _sse("system_failed", {
                "role": "system",
                "conversation_id": conversation_id,
                "thread_id": thread_id,
                "task_id": "",
                "item_id": "",
                "metadata": {},
                "payload": {"content": f"分析失败: {exc}"},
            })
            _persist("system", "system_failed", json.dumps({"error": str(exc)}, ensure_ascii=False))
            update_conversation_status(conversation_id, "failed")

        # 4. reasoning_completed
        yield _sse("reasoning_completed", {
            "conversation_id": conversation_id,
            "thread_id": thread_id,
            "task_id": "",
            "item_id": "",
        })

        # 5. done
        yield _sse("done", {"conversation_id": conversation_id, "thread_id": thread_id})

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
