"""SSE stream tests - verify /api/v1/agents/stream event sequence per intent.

Covers three paths per integration spec:
  - chat: conversation_started -> message -> done
  - full_analysis: ... -> reasoning_started -> workflow_started -> agent_completed -> ...
  - error: ... -> system_failed -> done
"""

import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage

from valor.server.intent import IntentResult


def _parse_events(text: str) -> list[dict]:
    events = []
    for chunk in text.split("\n\n"):
        chunk = chunk.strip()
        if not chunk.startswith("data: "):
            continue
        events.append(json.loads(chunk[len("data: "):]))
    return events


async def _chat_intent(query):
    return IntentResult(intent="chat", reply="您好！请提供股票代码。")


def test_sse_chat_returns_conversation_started_and_done(client, monkeypatch):
    monkeypatch.setattr("valor.server.routes.stream.classify_intent", _chat_intent)

    r = client.post("/api/v1/agents/stream", json={"query": "你好"})
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("text/event-stream")

    events = _parse_events(r.text)
    types = [e["event"] for e in events]
    assert types[0] == "conversation_started"
    assert "message" in types
    assert types[-1] == "done"


async def _full_analysis_intent(query):
    return IntentResult(intent="full_analysis", ticker="600519")


def test_sse_full_analysis_emits_streaming_events(client, monkeypatch):
    """Full_analysis now uses streaming: workflow_started → agent_completed → workflow_completed."""
    fake_chunks = [
        {"market_data": {"data": {"ticker": "600519", "price": 1685.0}}},
        {"portfolio_manager": {
            "messages": [SimpleNamespace(
                name="portfolio_management_agent",
                content='{"action": "buy", "quantity": 100, "confidence": 0.72}',
            )]
        }},
    ]

    monkeypatch.setattr("valor.server.routes.stream.classify_intent", _full_analysis_intent)
    monkeypatch.setattr("valor.server.routes.stream.stream_analysis", _make_fake_stream(fake_chunks))

    r = client.post(
        "/api/v1/agents/stream",
        json={"query": "分析600519", "agent_name": "ValorAgent"},
    )
    assert r.status_code == 200
    events = _parse_events(r.text)
    types = [e["event"] for e in events]

    assert types[0] == "conversation_started"
    assert "thread_started" in types
    assert "reasoning_started" in types
    assert "workflow_started" in types
    assert "agent_completed" in types
    assert "workflow_completed" in types
    assert "reasoning_completed" in types
    assert types[-1] == "done"


def _boom_stream(**kwargs):
    raise RuntimeError("workflow exploded")
    yield  # unreachable, makes this a generator


def test_sse_workflow_exception_emits_system_failed(client, monkeypatch):
    monkeypatch.setattr("valor.server.routes.stream.classify_intent", _full_analysis_intent)
    monkeypatch.setattr("valor.server.routes.stream.stream_analysis", _boom_stream)

    r = client.post(
        "/api/v1/agents/stream",
        json={"query": "分析600519", "agent_name": "ValorAgent"},
    )
    assert r.status_code == 200
    events = _parse_events(r.text)
    types = [e["event"] for e in events]

    assert "system_failed" in types
    assert types[-1] == "done"
    failed = next(e for e in events if e["event"] == "system_failed")
    assert "workflow exploded" in failed["data"]["payload"]["content"]


def _make_fake_stream(chunks):
    """Helper: create a fake stream_analysis generator yielding chunks."""
    def fake_stream(**kwargs):
        for chunk in chunks:
            yield chunk
    return fake_stream


def _parse_sse_events(response_text: str) -> list[dict]:
    """Parse SSE response text into list of {event, data} dicts."""
    events = []
    for line in response_text.split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            payload = json.loads(line[6:])
            events.append(payload)
    return events


def _fake_classify_full_analysis(query: str):
    """Fake classify_intent that returns full_analysis intent with ticker."""
    async def _async():
        return type("Intent", (), {
            "intent": "full_analysis",
            "ticker": "600519",
            "agent": None,
            "reply": None,
        })()
    return _async()


@pytest.fixture
def fake_full_analysis_chunks():
    """3 fake chunks: market_data, technicals, portfolio_manager (with decision)."""
    return [
        {"market_data": {"data": {"ticker": "600519", "price": 1685.0}}},
        {"technicals": {"data": {"signal": "bullish", "rsi": 65.0}}},
        {"portfolio_manager": {
            "messages": [HumanMessage(
                content=json.dumps({"action": "buy", "quantity": 100, "confidence": 0.72}),
                name="portfolio_management_agent",
            )]
        }},
    ]


def test_full_analysis_emits_workflow_started_first(client, monkeypatch, fake_full_analysis_chunks):
    """workflow_started must be the first event (after conversation_started/message/thread_started)."""
    def fake_stream(**kwargs):
        for chunk in fake_full_analysis_chunks:
            yield chunk

    async def fake_classify(query):
        return type("Intent", (), {
            "intent": "full_analysis",
            "ticker": "600519",
            "agent": None,
            "reply": None,
        })()

    monkeypatch.setattr("valor.server.routes.stream.stream_analysis", fake_stream)
    monkeypatch.setattr("valor.server.routes.stream.classify_intent", fake_classify)

    response = client.post(
        "/api/v1/agents/stream",
        json={"query": "600519", "agent_name": "ValorAgent"},
    )
    assert response.status_code == 200

    events = _parse_sse_events(response.text)
    event_types = [e["event"] for e in events]

    # workflow_started must come before agent_completed
    ws_idx = event_types.index("workflow_started")
    ac_idx = event_types.index("agent_completed")
    assert ws_idx < ac_idx


def test_full_analysis_emits_agent_completed_per_node(client, monkeypatch, fake_full_analysis_chunks):
    """One agent_completed event per yielded chunk."""
    def fake_stream(**kwargs):
        for chunk in fake_full_analysis_chunks:
            yield chunk

    async def fake_classify(query):
        return type("Intent", (), {
            "intent": "full_analysis",
            "ticker": "600519",
            "agent": None,
            "reply": None,
        })()

    monkeypatch.setattr("valor.server.routes.stream.stream_analysis", fake_stream)
    monkeypatch.setattr("valor.server.routes.stream.classify_intent", fake_classify)

    response = client.post(
        "/api/v1/agents/stream",
        json={"query": "600519", "agent_name": "ValorAgent"},
    )

    events = _parse_sse_events(response.text)
    agent_events = [e for e in events if e["event"] == "agent_completed"]

    assert len(agent_events) == 3
    agent_names = [e["data"]["agent"] for e in agent_events]
    assert agent_names == ["market_data", "technicals", "portfolio_manager"]


def test_full_analysis_emits_workflow_completed_with_decision(client, monkeypatch, fake_full_analysis_chunks):
    """workflow_completed must carry final_decision extracted from portfolio_manager message."""
    def fake_stream(**kwargs):
        for chunk in fake_full_analysis_chunks:
            yield chunk

    async def fake_classify(query):
        return type("Intent", (), {
            "intent": "full_analysis",
            "ticker": "600519",
            "agent": None,
            "reply": None,
        })()

    monkeypatch.setattr("valor.server.routes.stream.stream_analysis", fake_stream)
    monkeypatch.setattr("valor.server.routes.stream.classify_intent", fake_classify)

    response = client.post(
        "/api/v1/agents/stream",
        json={"query": "600519", "agent_name": "ValorAgent"},
    )

    events = _parse_sse_events(response.text)
    wf_completed = next(e for e in events if e["event"] == "workflow_completed")

    assert wf_completed["data"]["final_decision"] is not None
    assert wf_completed["data"]["final_decision"]["action"] == "buy"
    assert wf_completed["data"]["final_decision"]["quantity"] == 100
    assert wf_completed["data"]["final_decision"]["confidence"] == 0.72


def test_full_analysis_emits_done_last(client, monkeypatch, fake_full_analysis_chunks):
    """done must be the final event."""
    def fake_stream(**kwargs):
        for chunk in fake_full_analysis_chunks:
            yield chunk

    async def fake_classify(query):
        return type("Intent", (), {
            "intent": "full_analysis",
            "ticker": "600519",
            "agent": None,
            "reply": None,
        })()

    monkeypatch.setattr("valor.server.routes.stream.stream_analysis", fake_stream)
    monkeypatch.setattr("valor.server.routes.stream.classify_intent", fake_classify)

    response = client.post(
        "/api/v1/agents/stream",
        json={"query": "600519", "agent_name": "ValorAgent"},
    )

    events = _parse_sse_events(response.text)
    assert events[-1]["event"] == "done"


def test_full_analysis_failure_emits_system_failed(client, monkeypatch):
    """When stream_analysis raises, system_failed + done must be emitted."""
    def fake_stream(**kwargs):
        raise RuntimeError("LLM timeout")
        yield  # unreachable, makes this a generator

    async def fake_classify(query):
        return type("Intent", (), {
            "intent": "full_analysis",
            "ticker": "600519",
            "agent": None,
            "reply": None,
        })()

    monkeypatch.setattr("valor.server.routes.stream.stream_analysis", fake_stream)
    monkeypatch.setattr("valor.server.routes.stream.classify_intent", fake_classify)

    response = client.post(
        "/api/v1/agents/stream",
        json={"query": "600519", "agent_name": "ValorAgent"},
    )

    events = _parse_sse_events(response.text)
    event_types = [e["event"] for e in events]

    assert "system_failed" in event_types
    assert event_types[-1] == "done"


def test_workflow_started_carries_agent_list(client, monkeypatch, fake_full_analysis_chunks):
    """workflow_started payload must include the 12 agent names."""
    def fake_stream(**kwargs):
        for chunk in fake_full_analysis_chunks:
            yield chunk

    async def fake_classify(query):
        return type("Intent", (), {
            "intent": "full_analysis",
            "ticker": "600519",
            "agent": None,
            "reply": None,
        })()

    monkeypatch.setattr("valor.server.routes.stream.stream_analysis", fake_stream)
    monkeypatch.setattr("valor.server.routes.stream.classify_intent", fake_classify)

    response = client.post(
        "/api/v1/agents/stream",
        json={"query": "600519", "agent_name": "ValorAgent"},
    )

    events = _parse_sse_events(response.text)
    ws = next(e for e in events if e["event"] == "workflow_started")

    assert len(ws["data"]["agents"]) == 9
    assert "market_data" in ws["data"]["agents"]
    assert "portfolio_manager" in ws["data"]["agents"]
    assert ws["data"]["ticker"] == "600519"


def test_bull_bear_debate_emits_three_sub_events(client, monkeypatch):
    """bull_bear_debate node must emit 3 dot-namespaced agent_completed events."""
    from langchain_core.messages import HumanMessage

    fake_chunks = [
        {"market_data": {"data": {"ticker": "600519"}}},
        {"bull_bear_debate": {
            "messages": [
                HumanMessage(content='{"signal":"bullish","confidence":0.7}', name="bull_case_agent"),
                HumanMessage(content='{"signal":"bearish","confidence":0.4}', name="bear_case_agent"),
                HumanMessage(content='{"signal":"bullish","confidence":0.65}', name="bull_bear_debate_agent"),
            ],
            "data": {},
        }},
        {"portfolio_manager": {
            "messages": [HumanMessage(content='{"action":"buy","quantity":100}', name="portfolio_management_agent")]
        }},
    ]

    def fake_stream(**kwargs):
        for chunk in fake_chunks:
            yield chunk

    async def fake_classify(query):
        return type("Intent", (), {
            "intent": "full_analysis",
            "ticker": "600519",
            "agent": None,
            "reply": None,
        })()

    monkeypatch.setattr("valor.server.routes.stream.stream_analysis", fake_stream)
    monkeypatch.setattr("valor.server.routes.stream.classify_intent", fake_classify)

    response = client.post(
        "/api/v1/agents/stream",
        json={"query": "600519", "agent_name": "ValorAgent"},
    )
    events = _parse_sse_events(response.text)
    agent_events = [e for e in events if e["event"] == "agent_completed"]
    agent_names = [e["data"]["agent"] for e in agent_events]

    assert "bull_bear_debate.bull" in agent_names
    assert "bull_bear_debate.bear" in agent_names
    assert "bull_bear_debate.verdict" in agent_names
    assert "bull_bear_debate" not in agent_names  # parent doesn't emit its own event
