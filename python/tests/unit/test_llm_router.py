"""Tests for LLM router priority and fallback behavior."""

from unittest.mock import patch

import pytest

from valor.adapters.llm import get_llm_provider


def test_router_returns_first_available_provider():
    with patch.dict(
        "os.environ",
        {
            "VALOR_LLM_PROVIDER": "openai",
            "VALOR_OPENAI_API_KEY": "sk-test",
            "VALOR_OPENAI_BASE_URL": "https://api.test.com/v1",
        },
    ):
        provider = get_llm_provider()
        assert provider is not None


def test_router_raises_when_provider_not_registered(monkeypatch):
    monkeypatch.setenv("VALOR_LLM_PROVIDER", "nonexistent_provider")
    with pytest.raises(RuntimeError, match="no LLM provider"):
        get_llm_provider()
