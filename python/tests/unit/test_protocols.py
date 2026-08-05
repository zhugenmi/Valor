"""Tests for core protocol Pydantic models.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

import pytest
from pydantic import ValidationError

from valor.core.protocols import Action, Citation, Message, Signal


def test_signal_valid_bullish():
    sig = Signal(
        agent="Technical Analysis",
        signal="bullish",
        confidence=0.8,
        reasoning="MACD golden cross",
    )
    assert sig.agent == "Technical Analysis"
    assert sig.signal == "bullish"
    assert sig.confidence == 0.8


def test_signal_invalid_signal_value():
    with pytest.raises(ValidationError):
        Signal(agent="X", signal="invalid", confidence=0.5, reasoning="")


def test_signal_confidence_out_of_range():
    with pytest.raises(ValidationError):
        Signal(agent="X", signal="bullish", confidence=1.5, reasoning="")
    with pytest.raises(ValidationError):
        Signal(agent="X", signal="bullish", confidence=-0.1, reasoning="")


def test_action_valid_buy():
    action = Action(
        action="buy",
        quantity=100,
        confidence=0.7,
        agent_signals=[
            Signal(agent="Tech", signal="bullish", confidence=0.8, reasoning=""),
        ],
        reasoning="Bullish confluence",
    )
    assert action.action == "buy"
    assert len(action.agent_signals) == 1


def test_action_invalid_action_value():
    with pytest.raises(ValidationError):
        Action(action="hold_long", quantity=0, confidence=0.0, agent_signals=[], reasoning="")


def test_message_round_trip():
    msg = Message(role="user", content="Analyze 600519")
    assert msg.role == "user"
    assert msg.content == "Analyze 600519"


def test_signal_citations_default_empty():
    s = Signal(agent="test", signal="bullish", confidence=0.8, reasoning="x")
    assert s.citations == []


def test_signal_with_citations():
    c = Citation(chunk_id="c1", doc_id="d1", doc_title="研报",
                 publish_date="2024-10-28", vintage="current", cited_text="原文片段")
    s = Signal(agent="test", signal="bullish", confidence=0.8, reasoning="x", citations=[c])
    assert len(s.citations) == 1
    assert s.citations[0].chunk_id == "c1"


def test_citation_serialization():
    c = Citation(chunk_id="c1", doc_id="d1", doc_title="t",
                 publish_date="2024-01-01", vintage="current", cited_text="x", page_no=3)
    d = c.model_dump()
    assert d["page_no"] == 3
    assert d["vintage"] == "current"