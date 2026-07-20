"""Integration test for diagnosis SSE flow. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from valor.server.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _parse_sse(text: str):
    """Parse SSE text into list of {event, data} dicts."""
    events = []
    for block in text.split("\n\n"):
        if not block.startswith("data: "):
            continue
        import json
        payload = json.loads(block[len("data: "):])
        events.append(payload)
    return events


def test_diagnosis_injects_portfolio_and_emits_preflight(client):
    """POST /agents/stream with portfolio_id+ticker should:
    1. Emit data_preflight event with trading_day + filled
    2. Pass real portfolio to stream_analysis
    3. Persist messages
    """
    body = {
        "query": "诊断股票600519",
        "agent_name": "ValorAgent",
        "portfolio_id": "pf_test1",
        "ticker": "600519",
    }

    fake_intent = MagicMock()
    fake_intent.intent = "full_analysis"
    fake_intent.ticker = "600519"
    fake_intent.agent = None

    def _fake_stream_analysis(**kwargs):
        # Yield one chunk to simulate workflow
        yield {"market_data": {"data": {"ticker": "600519"}}}

    with (
        patch("valor.server.routes.stream.classify_intent", return_value=fake_intent),
        patch(
            "valor.server.routes.stream.load_portfolio_context",
            return_value={"cash": 50000.0, "stock": 100},
        ) as mock_load_pf,
        patch(
            "valor.server.routes.stream.ensure_latest_trading_day_data",
            return_value={"trading_day": "2026-07-17", "filled": False},
        ),
        patch(
            "valor.server.routes.stream.stream_analysis",
            side_effect=_fake_stream_analysis,
        ) as mock_stream,
        patch("valor.server.routes.stream.create_conversation") as mock_create,
        patch("valor.server.routes.stream.append_message") as mock_append,
        patch("valor.server.routes.stream.update_conversation_status") as mock_update,
    ):
        resp = client.post("/api/v1/agents/stream", json=body)
        text = resp.text

    events = _parse_sse(text)
    event_names = [e["event"] for e in events]

    # 1. preflight emitted
    assert "data_preflight" in event_names
    preflight_event = next(e for e in events if e["event"] == "data_preflight")
    assert preflight_event["data"]["trading_day"] == "2026-07-17"
    assert preflight_event["data"]["filled"] is False

    # 2. portfolio context loaded with correct args
    mock_load_pf.assert_called_once_with("pf_test1", "600519")

    # 3. stream_analysis called with portfolio dict
    _, kwargs = mock_stream.call_args
    assert kwargs.get("portfolio") == {"cash": 50000.0, "stock": 100}

    # 4. conversation created + messages appended + status updated
    mock_create.assert_called_once()
    assert mock_append.call_count >= 2  # at least user msg + one agent event
    mock_update.assert_called()


def test_diagnosis_without_portfolio_id_uses_defaults(client):
    """Without portfolio_id, should NOT call load_portfolio_context; portfolio
    falls back to current default {cash:100000, stock:0}."""
    body = {
        "query": "分析600519",
        "agent_name": "ValorAgent",
    }
    fake_intent = MagicMock()
    fake_intent.intent = "full_analysis"
    fake_intent.ticker = "600519"

    def _fake_stream(**kwargs):
        yield {"market_data": {"data": {"ticker": "600519"}}}

    with (
        patch("valor.server.routes.stream.classify_intent", return_value=fake_intent),
        patch("valor.server.routes.stream.load_portfolio_context") as mock_load,
        patch(
            "valor.server.routes.stream.ensure_latest_trading_day_data",
            return_value={"trading_day": "2026-07-17", "filled": False},
        ),
        patch("valor.server.routes.stream.stream_analysis", side_effect=_fake_stream),
        patch("valor.server.routes.stream.create_conversation"),
        patch("valor.server.routes.stream.append_message"),
        patch("valor.server.routes.stream.update_conversation_status"),
    ):
        resp = client.post("/api/v1/agents/stream", json=body)
        resp.text

    mock_load.assert_not_called()


def test_diagnosis_portfolio_not_found_emits_system_failed(client):
    """If portfolio_id doesn't exist, should emit system_failed and not run workflow."""
    from valor.portfolio.storage import PortfolioNotFound

    body = {
        "query": "诊断股票600519",
        "agent_name": "ValorAgent",
        "portfolio_id": "pf_missing",
        "ticker": "600519",
    }
    fake_intent = MagicMock()
    fake_intent.intent = "full_analysis"
    fake_intent.ticker = "600519"

    with (
        patch("valor.server.routes.stream.classify_intent", return_value=fake_intent),
        patch(
            "valor.server.routes.stream.load_portfolio_context",
            side_effect=PortfolioNotFound("pf_missing"),
        ),
        patch("valor.server.routes.stream.stream_analysis") as mock_stream,
        patch("valor.server.routes.stream.create_conversation"),
        patch("valor.server.routes.stream.append_message"),
        patch("valor.server.routes.stream.update_conversation_status") as mock_update,
    ):
        resp = client.post("/api/v1/agents/stream", json=body)
        text = resp.text

    events = _parse_sse(text)
    event_names = [e["event"] for e in events]
    assert "system_failed" in event_names
    mock_stream.assert_not_called()
    # Status updated to 'failed'
    statuses = [c.args[1] for c in mock_update.call_args_list]
    assert "failed" in statuses
