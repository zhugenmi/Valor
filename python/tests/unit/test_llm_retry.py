"""Unit tests for LLM retry logic in openrouter_config.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from valor.tools.openrouter_config import get_chat_completion


def _fake_provider_with_side_effect(side_effect):
    provider = AsyncMock()
    provider.chat.side_effect = side_effect
    return provider


def test_retry_on_read_timeout_then_success():
    """前两次抛 ReadTimeout，第三次成功 -> 应重试并返回成功结果。"""
    provider = _fake_provider_with_side_effect(
        [httpx.ReadTimeout("timeout"), httpx.ReadTimeout("timeout"), "ok"]
    )
    with patch(
        "valor.tools.openrouter_config.get_llm_provider",
        return_value=provider,
    ):
        result = get_chat_completion(
            [{"role": "user", "content": "hi"}],
            max_retries=3,
            initial_retry_delay=0,
        )
    assert result == "ok"
    assert provider.chat.call_count == 3


def test_retry_on_connect_error_then_success():
    """ConnectError 也应触发重试。"""
    provider = _fake_provider_with_side_effect(
        [httpx.ConnectError("conn refused"), "ok"]
    )
    with patch(
        "valor.tools.openrouter_config.get_llm_provider",
        return_value=provider,
    ):
        result = get_chat_completion(
            [{"role": "user", "content": "hi"}],
            max_retries=3,
            initial_retry_delay=0,
        )
    assert result == "ok"
    assert provider.chat.call_count == 2


def test_no_retry_on_runtime_error():
    """非网络错误的 RuntimeError 不应重试，直接抛出。"""
    provider = _fake_provider_with_side_effect(
        RuntimeError("non-retryable business error")
    )
    with patch(
        "valor.tools.openrouter_config.get_llm_provider",
        return_value=provider,
    ):
        with pytest.raises(RuntimeError, match="LLM chat failed"):
            get_chat_completion(
                [{"role": "user", "content": "hi"}],
                max_retries=3,
                initial_retry_delay=0,
            )
    assert provider.chat.call_count == 1


def test_retry_exhausted_raises_runtime_error():
    """重试耗尽后应抛 RuntimeError。"""
    provider = _fake_provider_with_side_effect(
        [httpx.ReadTimeout("timeout")] * 3
    )
    with patch(
        "valor.tools.openrouter_config.get_llm_provider",
        return_value=provider,
    ):
        with pytest.raises(RuntimeError, match="after 3 retries"):
            get_chat_completion(
                [{"role": "user", "content": "hi"}],
                max_retries=3,
                initial_retry_delay=0,
            )
    assert provider.chat.call_count == 3


def test_retry_on_wrapped_runtime_error():
    """provider 把 httpx 异常包装成 RuntimeError 时，通过 __cause__ 识别重试。"""
    original = httpx.ReadTimeout("underlying timeout")
    wrapped = RuntimeError("LLM chat failed").__class__("wrapped")
    wrapped.__cause__ = original

    provider = _fake_provider_with_side_effect([wrapped, "ok"])
    with patch(
        "valor.tools.openrouter_config.get_llm_provider",
        return_value=provider,
    ):
        result = get_chat_completion(
            [{"role": "user", "content": "hi"}],
            max_retries=3,
            initial_retry_delay=0,
        )
    assert result == "ok"
    assert provider.chat.call_count == 2
