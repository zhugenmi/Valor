"""Test intent classifier recognizes 诊断 keyword. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from valor.server.intent import classify_intent


async def _mock_chat(**_kwargs):
    return '{"intent": "full_analysis", "ticker": "600519", "agent": null, "reply": null}'


async def test_diagnosis_keyword_triggers_full_analysis():
    with patch("valor.server.intent.get_llm_provider") as mock_provider:
        mock_provider.return_value.chat = AsyncMock(side_effect=_mock_chat)
        result = await classify_intent("诊断股票600519")
    assert result.intent == "full_analysis"
    assert result.ticker == "600519"
    assert result.agent is None


async def test_diagnosis_fallback_regex():
    """When LLM unavailable, regex fallback should still extract ticker."""
    with patch("valor.server.intent.get_llm_provider", side_effect=RuntimeError("no provider")):
        result = await classify_intent("诊断股票600519")
    assert result.intent == "full_analysis"
    assert result.ticker == "600519"