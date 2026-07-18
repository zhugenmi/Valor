"""Tests for the api_utils compatibility shim."""

from valor.utils.api_utils import agent_endpoint, log_llm_interaction


def test_agent_endpoint_decorates_and_passes_state():
    """agent_endpoint should wrap a function and pass through AgentState."""

    @agent_endpoint("test_agent", "A test agent")
    def my_agent(state):
        return {"result": "done", "name": state["metadata"]["current_agent_name"]}

    result = my_agent({"metadata": {"show_reasoning": False}})
    assert result["result"] == "done"
    assert result["name"] == "test_agent"


def test_agent_endpoint_preserves_function_metadata():
    """agent_endpoint should preserve __name__ and __doc__."""

    @agent_endpoint("my_agent", "Does something")
    def real_func(state):
        """Real docstring."""
        return state

    assert real_func.__name__ == "real_func"
    assert real_func.__doc__ == "Real docstring."


def test_log_llm_interaction_decorator_pass_through():
    """log_llm_interaction as decorator should pass through call results."""

    @log_llm_interaction
    def llm_call(text):
        return f"response: {text}"

    result = llm_call("hello")
    assert result == "response: hello"


def test_log_llm_interaction_with_state():
    """log_llm_interaction with state dict should still work."""

    @log_llm_interaction({"some_state": True})
    def llm_call(text):
        return f"echo: {text}"

    result = llm_call("ping")
    assert result == "echo: ping"
