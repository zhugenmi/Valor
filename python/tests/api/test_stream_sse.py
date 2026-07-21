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


async def _single_multi_agent_intent(query):
    return IntentResult(
        intent="single_analysis",
        ticker="600519",
        agents=["technicals", "valuation"],
    )


def _make_fake_run_agents_multi():
    """Fake run_agents returning messages for technicals + valuation."""
    from types import SimpleNamespace
    def _fake(**_kwargs):
        return {
            "messages": [
                SimpleNamespace(
                    name="technical_analyst_agent",
                    content='{"signal": "buy", "confidence": 0.7}',
                ),
                SimpleNamespace(
                    name="valuation_agent",
                    content='{"intrinsic_value": 1800, "margin_of_safety": 0.1}',
                ),
            ],
            "data": {},
            "metadata": {},
        }
    return _fake


def test_sse_single_analysis_multi_agent_emits_component_generator_per_agent(
    client, monkeypatch
):
    """single_analysis 多 agent 应为每个 agent yield 一个 component_generator，item_id 唯一。"""
    monkeypatch.setattr("valor.server.routes.stream.classify_intent", _single_multi_agent_intent)
    monkeypatch.setattr("valor.server.routes.stream.run_agents", _make_fake_run_agents_multi())

    r = client.post(
        "/api/v1/agents/stream",
        json={"query": "五粮液技术面和估值", "agent_name": "ValorAgent"},
    )
    assert r.status_code == 200
    events = _parse_events(r.text)
    component_events = [e for e in events if e["event"] == "component_generator"]
    assert len(component_events) == 2

    item_ids = [e["data"]["item_id"] for e in component_events]
    assert len(set(item_ids)) == 2  # 唯一

    # metadata 带 agent_name
    agent_names = [e["data"]["metadata"]["agent_name"] for e in component_events]
    assert set(agent_names) == {"technicals", "valuation"}


async def _single_empty_agents_intent(query):
    return IntentResult(intent="single_analysis", ticker="600519", agents=[])


def test_sse_single_analysis_empty_agents_falls_back_to_full_analysis(
    client, monkeypatch
):
    """agents=[] 时应回退到 full_analysis（yield workflow_started）。"""
    monkeypatch.setattr("valor.server.routes.stream.classify_intent", _single_empty_agents_intent)
    fake_chunks = [
        {"market_data": {"data": {"ticker": "600519"}}},
        {"portfolio_manager": {
            "messages": [SimpleNamespace(
                name="portfolio_management_agent",
                content='{"action": "hold", "quantity": 0}',
            )]
        }},
    ]
    monkeypatch.setattr("valor.server.routes.stream.stream_analysis", _make_fake_stream(fake_chunks))

    r = client.post(
        "/api/v1/agents/stream",
        json={"query": "五粮液", "agent_name": "ValorAgent"},
    )
    assert r.status_code == 200
    events = _parse_events(r.text)
    types = [e["event"] for e in events]
    assert "workflow_started" in types


def _make_fake_run_agents_with_failure():
    """Fake run_agents where technicals failed, valuation succeeded."""
    from types import SimpleNamespace
    def _fake(**_kwargs):
        return {
            "messages": [
                SimpleNamespace(
                    name="technical_analyst_agent",
                    content='{"error": "data fetch failed"}',
                ),
                SimpleNamespace(
                    name="valuation_agent",
                    content='{"intrinsic_value": 1800}',
                ),
            ],
            "data": {},
            "metadata": {},
        }
    return _fake


def test_sse_single_analysis_failed_agent_emits_agent_failed(client, monkeypatch):
    """失败的 agent 应 yield agent_failed，其他 agent 仍 component_generator。"""
    monkeypatch.setattr("valor.server.routes.stream.classify_intent", _single_multi_agent_intent)
    monkeypatch.setattr("valor.server.routes.stream.run_agents", _make_fake_run_agents_with_failure())

    r = client.post(
        "/api/v1/agents/stream",
        json={"query": "五粮液技术面和估值", "agent_name": "ValorAgent"},
    )
    assert r.status_code == 200
    events = _parse_events(r.text)
    failed_events = [e for e in events if e["event"] == "agent_failed"]
    component_events = [e for e in events if e["event"] == "component_generator"]

    assert len(failed_events) == 1
    assert failed_events[0]["data"]["agent"] == "technicals"
    assert len(component_events) == 1
    assert component_events[0]["data"]["metadata"]["agent_name"] == "valuation"
