"""Tests for the serialization utility."""

from valor.utils.serialization import serialize_agent_state


def test_serialize_empty_state():
    """Empty state should return empty dict."""
    assert serialize_agent_state({}) == {}


def test_serialize_none():
    """None/Falsey state should return empty dict."""
    assert serialize_agent_state(None) == {}


def test_serialize_basic_types():
    """Simple types should pass through."""
    state = {"key": "value", "number": 42, "flag": True}
    result = serialize_agent_state(state)
    assert result["key"] == "value"
    assert result["number"] == 42
    assert result["flag"] is True


def test_serialize_nested():
    """Nested dicts should be recursively serialized."""
    state = {"outer": {"inner": "deep", "list": [1, 2, 3]}}
    result = serialize_agent_state(state)
    assert result["outer"]["inner"] == "deep"
    assert result["outer"]["list"] == [1, 2, 3]


def test_serialize_fallback():
    """Unserializable objects should fall back to string."""
    state = {"obj": Exception("test")}
    result = serialize_agent_state(state)
    assert isinstance(result["obj"], str)
