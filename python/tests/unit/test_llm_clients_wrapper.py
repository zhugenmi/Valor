"""Tests for llm_clients wrapper that delegates to adapters/llm."""

from unittest.mock import AsyncMock, patch

from valor.utils.llm_clients import call_llm, get_llm


def test_get_llm_delegates_to_get_llm_provider():
    with patch("valor.utils.llm_clients.get_llm_provider") as mock:
        get_llm()
        mock.assert_called_once()


def test_call_llm_returns_response_string():
    fake_provider = AsyncMock()
    fake_provider.chat.return_value = "fake response"

    with patch("valor.utils.llm_clients.get_llm_provider", return_value=fake_provider):
        result = call_llm("hello")
    assert result == "fake response"
    fake_provider.chat.assert_called_once()


def test_call_llm_with_system_prompt():
    fake_provider = AsyncMock()
    fake_provider.chat.return_value = "helpful response"

    with patch("valor.utils.llm_clients.get_llm_provider", return_value=fake_provider):
        result = call_llm("hello", system="be helpful")

    assert result == "helpful response"
    fake_provider.chat.assert_called_once()
    messages = fake_provider.chat.call_args[0][0]
    assert len(messages) == 2
    assert messages[0].role == "system"
    assert messages[0].content == "be helpful"
    assert messages[1].role == "user"
    assert messages[1].content == "hello"
