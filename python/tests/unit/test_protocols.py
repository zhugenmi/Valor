"""Tests for core protocol Pydantic models."""

import pytest
from pydantic import ValidationError

from valor.core.protocols import Action, Message, Signal


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