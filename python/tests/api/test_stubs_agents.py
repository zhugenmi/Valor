"""Tests for agents stub endpoints. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations


def test_list_agents_excludes_valor_agent(client):
    """ValorAgent 是主 agent，不应出现在 Agent 市场列表。"""
    r = client.get("/api/v1/agents/")
    assert r.status_code == 200
    body = r.json()
    agent_names = [a["agent_name"] for a in body["data"]["agents"]]
    assert "ValorAgent" not in agent_names
    # 其他 agent 仍在
    assert "sentiment_analysis" in agent_names


def test_agent_by_name_valor_agent_returns_404(client):
    """ValorAgent 不在市场，by-name 查询应 404。前端 api/agent.ts 对 ValorAgent 硬编码短路。"""
    r = client.get("/api/v1/agents/by-name/ValorAgent")
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 404
