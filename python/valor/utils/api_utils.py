"""API utilities - simplified shim for A_Share agent compatibility (no backend dependency).

Agents migrated from A_Share use @agent_endpoint and log_llm_interaction decorators.
This module provides minimal versions that work without the FastAPI backend.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

import functools
from typing import Any

from loguru import logger


def agent_endpoint(agent_name: str, description: str = "") -> Any:
    """Decorator that wraps an agent function for workflow compatibility.

    Simplified version - does not register with backend or capture stdout.
    The real agent execution logging will be added when the FastAPI server is wired.
    """

    def decorator(agent_func):
        @functools.wraps(agent_func)
        def wrapper(state, *args, **kwargs):
            state["metadata"]["current_agent_name"] = agent_name
            logger.debug("Agent {name} executing", name=agent_name)
            result = agent_func(state, *args, **kwargs)
            return result

        return wrapper

    return decorator


def log_llm_interaction(state: Any = None) -> Any:
    """Decorator/factory for LLM interaction logging (simplified pass-through).

    Supports three call patterns:
      @log_llm_interaction                    # bare decorator, no args
      @log_llm_interaction()                   # decorator with no state
      @log_llm_interaction({"state": ...})     # decorator with state dict
      log_llm_interaction(state)(func)(args)   # direct call pattern
      log_llm_interaction("agent_name")        # direct logger

    In all cases the wrapped function is called as-is (no real backend logging).
    """

    def _make_decorator(llm_func):
        @functools.wraps(llm_func)
        def wrapper(*args, **kwargs):
            logger.debug(
                "LLM call: {name}",
                name=llm_func.__name__,
            )
            return llm_func(*args, **kwargs)

        return wrapper

    # Pattern 1: @log_llm_interaction (bare decorator, state is the function)
    if callable(state):
        return _make_decorator(state)

    # Pattern 2: log_llm_interaction("agent_name") -> direct logger
    if isinstance(state, str):
        return lambda req, resp: resp

    # Pattern 3: @log_llm_interaction() or @log_llm_interaction({...})
    return _make_decorator
