"""Tests for workflow streaming - stream_analysis() and _build_initial_state().

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from typing import Iterator

from langchain_core.messages import HumanMessage

from valor.agents.workflow import (
    _build_initial_state,
    run_analysis,
    stream_analysis,
)


def test_build_initial_state_returns_correct_structure():
    state = _build_initial_state(ticker="600519")
    assert "messages" in state
    assert "data" in state
    assert "metadata" in state
    assert state["data"]["ticker"] == "600519"
    assert state["data"]["start_date"] == ""
    assert state["data"]["end_date"] == ""
    assert state["data"]["portfolio"] == {"cash": 100000.0, "stock": 0}
    assert state["metadata"]["model"] == "openai"
    assert state["metadata"]["show_reasoning"] is False


def test_build_initial_state_default_portfolio_when_none():
    state = _build_initial_state(ticker="600519", portfolio=None)
    assert state["data"]["portfolio"] == {"cash": 100000.0, "stock": 0}


def test_build_initial_state_custom_portfolio_preserved():
    state = _build_initial_state(ticker="600519", portfolio={"cash": 50000.0, "stock": 100})
    assert state["data"]["portfolio"] == {"cash": 50000.0, "stock": 100}


def test_build_initial_state_kwargs_merged_into_metadata():
    state = _build_initial_state(ticker="600519", num_of_news=10)
    assert state["metadata"]["num_of_news"] == 10


def test_stream_analysis_yields_chunks(monkeypatch):
    """stream_analysis() should yield one chunk per node, format {node_name: state_delta}."""
    fake_chunks = [
        {"market_data": {"data": {"ticker": "600519"}}},
        {"technicals": {"data": {"signal": "bullish"}}},
        {"portfolio_manager": {
            "messages": [HumanMessage(content='{"action":"buy","quantity":100}', name="portfolio_management_agent")]
        }},
    ]

    class FakeCompiled:
        def stream(self, initial_state: dict) -> Iterator[dict]:
            for chunk in fake_chunks:
                yield chunk

    class FakeWorkflow:
        def compile(self) -> FakeCompiled:
            return FakeCompiled()

    monkeypatch.setattr("valor.agents.workflow.build_workflow", lambda stage_callback=None: FakeWorkflow())

    chunks = list(stream_analysis(ticker="600519"))

    assert len(chunks) == 3
    assert "market_data" in chunks[0]
    assert "technicals" in chunks[1]
    assert "portfolio_manager" in chunks[2]


def test_stream_analysis_uses_build_initial_state(monkeypatch):
    """stream_analysis() must call _build_initial_state (same path as run_analysis)."""
    captured_state: list[dict] = []

    class FakeCompiled:
        def stream(self, initial_state: dict) -> Iterator[dict]:
            captured_state.append(initial_state)
            yield {"market_data": {"data": {}}}

    class FakeWorkflow:
        def compile(self) -> FakeCompiled:
            return FakeCompiled()

    monkeypatch.setattr("valor.agents.workflow.build_workflow", lambda stage_callback=None: FakeWorkflow())

    list(stream_analysis(ticker="600519", portfolio={"cash": 50000.0, "stock": 0}, model="deepseek"))

    assert len(captured_state) == 1
    assert captured_state[0]["data"]["ticker"] == "600519"
    assert captured_state[0]["data"]["portfolio"]["cash"] == 50000.0
    assert captured_state[0]["metadata"]["model"] == "deepseek"


def test_run_analysis_still_works_after_refactor(monkeypatch):
    """Regression: run_analysis() must still produce final state via compiled.invoke()."""
    expected_result = {"messages": [], "data": {"ticker": "600519"}, "metadata": {}}

    class FakeCompiled:
        def invoke(self, initial_state: dict) -> dict:
            return expected_result

    class FakeWorkflow:
        def compile(self) -> FakeCompiled:
            return FakeCompiled()

    monkeypatch.setattr("valor.agents.workflow.build_workflow", lambda stage_callback=None: FakeWorkflow())

    result = run_analysis(ticker="600519")
    assert result == expected_result


def test_stream_analysis_forwards_stage_callback_to_build_workflow(monkeypatch):
    """stream_analysis() must pass stage_callback through to build_workflow."""
    captured_callback: list = []

    class FakeCompiled:
        def stream(self, initial_state: dict) -> Iterator[dict]:
            yield {"market_data": {"data": {}}}

    class FakeWorkflow:
        def compile(self) -> FakeCompiled:
            return FakeCompiled()

    def fake_build_workflow(stage_callback=None):
        captured_callback.append(stage_callback)
        return FakeWorkflow()

    monkeypatch.setattr("valor.agents.workflow.build_workflow", fake_build_workflow)

    def my_cb(sub_key, payload):
        pass

    list(stream_analysis(ticker="600519", stage_callback=my_cb))

    assert captured_callback == [my_cb]
