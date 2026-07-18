"""
Serialization utilities - convert complex Python objects to JSON-safe format.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from typing import Any


def _is_primitive(obj: Any) -> bool:
    return isinstance(obj, (int, float, bool, str, type(None)))


def _convert_to_serializable(obj: Any) -> Any:
    """Recursively convert objects to JSON-serializable format."""
    if _is_primitive(obj):
        return obj
    if isinstance(obj, (list, tuple)):
        return [_convert_to_serializable(item) for item in obj]
    if isinstance(obj, dict):
        return {str(key): _convert_to_serializable(value) for key, value in obj.items()}
    if hasattr(obj, "to_dict"):  # Pandas Series/DataFrame
        return obj.to_dict()
    if hasattr(obj, "content") and hasattr(obj, "type"):  # LangChain messages
        return {
            "content": _convert_to_serializable(obj.content),
            "type": obj.type,
        }
    # Check for custom objects AFTER primitives, so native types with __dict__
    # (like Exception subclasses) fall through to str()
    if hasattr(obj, "__dict__") and not isinstance(obj, BaseException):
        try:
            return _convert_to_serializable(obj.__dict__)
        except Exception:
            return str(obj)
    return str(obj)


def serialize_agent_state(state: dict) -> dict:
    """Convert AgentState to JSON-serializable dict."""
    if not state:
        return {}
    try:
        return _convert_to_serializable(state)
    except Exception as e:
        return {"error": f"cannot serialize state: {e}", "serialization_error": True}
