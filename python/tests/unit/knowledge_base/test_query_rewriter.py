"""Tests for query_rewriter. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from valor.knowledge_base.query_rewriter import rewrite_query, _parse_rewrites


def test_parse_rewrites_handles_newline_separated():
    """LLM 返回换行分隔的重写,应解析为列表。"""
    raw = "1. 贵州茅台营收是多少\n2. 茅台营业收入\n3. 贵州茅台 2024 营业总收入"
    result = _parse_rewrites(raw, original="贵州茅台营业收入", n=3)
    assert len(result) == 3
    assert "贵州茅台营收是多少" in result[0] or "贵州茅台营收" in result[0]


def test_parse_rewrites_strips_number_prefixes():
    """LLM 返回带数字前缀(如 '1. '),应去除。"""
    raw = "1. query one\n2. query two\n3. query three"
    result = _parse_rewrites(raw, original="original query", n=3)
    assert result == ["query one", "query two", "query three"]


def test_parse_rewrites_includes_original_when_short():
    """LLM 返回不足 N 条时,用原 query 补齐。"""
    raw = "重写一\n重写二"
    result = _parse_rewrites(raw, original="原 query", n=4)
    assert len(result) == 4
    assert "原 query" in result  # 原应在结果中
    assert "重写一" in result
    assert "重写二" in result


def test_rewrite_query_returns_original_only_when_llm_disabled(monkeypatch):
    """VALOR_KB_QUERY_REWRITE=0 时,只返回原 query。"""
    monkeypatch.setenv("VALOR_KB_QUERY_REWRITE", "0")
    result = rewrite_query("贵州茅台营业收入", n=3)
    assert result == ["贵州茅台营业收入"]


def test_rewrite_query_calls_llm_when_enabled(monkeypatch):
    """VALOR_KB_QUERY_REWRITE=1 时,调用 LLM 返回多个重写。"""
    monkeypatch.setenv("VALOR_KB_QUERY_REWRITE", "1")

    async def fake_chat(messages, **kwargs):
        return "1. 贵州茅台营收\n2. 茅台营业收入是多少\n3. 贵州茅台营业总收入"

    mock_provider = MagicMock()
    mock_provider.chat = fake_chat
    monkeypatch.setattr(
        "valor.knowledge_base.query_rewriter.get_llm_provider",
        lambda **kw: mock_provider,
    )

    result = rewrite_query("贵州茅台营业收入", n=3)
    assert len(result) == 3
    assert all(isinstance(q, str) for q in result)
    # 重写应与原 query 不同(至少有一个)
    assert any(q != "贵州茅台营业收入" for q in result)


def test_rewrite_query_falls_back_on_llm_error(monkeypatch):
    """LLM 调用失败时,回退到原 query。"""
    monkeypatch.setenv("VALOR_KB_QUERY_REWRITE", "1")

    async def failing_chat(messages, **kwargs):
        raise RuntimeError("LLM API timeout")

    mock_provider = MagicMock()
    mock_provider.chat = failing_chat
    monkeypatch.setattr(
        "valor.knowledge_base.query_rewriter.get_llm_provider",
        lambda **kw: mock_provider,
    )

    result = rewrite_query("任何 query", n=3)
    assert result == ["任何 query"]


def test_rewrite_query_caches_results(monkeypatch):
    """相同 query 多次调用只应触发一次 LLM(缓存生效)。"""
    monkeypatch.setenv("VALOR_KB_QUERY_REWRITE", "1")
    call_count = {"n": 0}

    async def counting_chat(messages, **kwargs):
        call_count["n"] += 1
        return "1. 重写一\n2. 重写二\n3. 重写三"

    mock_provider = MagicMock()
    mock_provider.chat = counting_chat
    monkeypatch.setattr(
        "valor.knowledge_base.query_rewriter.get_llm_provider",
        lambda **kw: mock_provider,
    )

    # 清空缓存
    from valor.knowledge_base import query_rewriter as qr
    qr._CACHE.clear()

    r1 = rewrite_query("同一 query", n=3)
    r2 = rewrite_query("同一 query", n=3)
    assert r1 == r2
    assert call_count["n"] == 1, f"缓存未生效,LLM 调用 {call_count['n']} 次"