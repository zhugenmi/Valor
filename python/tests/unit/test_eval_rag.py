"""Tests for eval_rag module. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Apply ragas compat shim before any ragas imports
sys.modules.setdefault("langchain_community.chat_models.vertexai", MagicMock())

from valor.knowledge_base.eval_rag import (  # noqa: E402
    BgeEmbeddings,
    rule_context_metrics,
    generate_answer,
    run_eval,
)


# ---------------------------------------------------------------------------
# rule_context_metrics
# ---------------------------------------------------------------------------

def test_rule_context_metrics_perfect():
    retrieved = ["c1", "c2", "c3"]
    gt = ["c1", "c2"]
    p, r = rule_context_metrics(retrieved, gt)
    assert p == pytest.approx(2 / 3, abs=0.01)
    assert r == 1.0


def test_rule_context_metrics_no_overlap():
    retrieved = ["c1", "c2"]
    gt = ["c3", "c4"]
    p, r = rule_context_metrics(retrieved, gt)
    assert p == 0.0
    assert r == 0.0


def test_rule_context_metrics_empty_retrieved():
    p, r = rule_context_metrics([], ["c1"])
    assert p == 0.0
    assert r == 0.0


def test_rule_context_metrics_partial_recall():
    retrieved = ["c1"]
    gt = ["c1", "c2", "c3"]
    p, r = rule_context_metrics(retrieved, gt)
    assert p == 1.0
    assert r == pytest.approx(1 / 3, abs=0.01)


# ---------------------------------------------------------------------------
# BgeEmbeddings wrapper
# ---------------------------------------------------------------------------

def test_bge_embeddings_dimensions():
    """bge-small-zh-v1.5 produces 512-dim normalized vectors."""
    emb = BgeEmbeddings()
    v = emb.embed_query("测试文本")
    assert len(v) == 512
    # Normalized: L2 norm ≈ 1
    norm = sum(x * x for x in v) ** 0.5
    assert norm == pytest.approx(1.0, abs=0.01)


def test_bge_embeddings_batch():
    emb = BgeEmbeddings()
    vecs = emb.embed_documents(["文本1", "文本2"])
    assert len(vecs) == 2
    assert all(len(v) == 512 for v in vecs)


# ---------------------------------------------------------------------------
# generate_answer (mock LLM)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_answer_with_mock_llm():
    from unittest.mock import AsyncMock
    mock_llm = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.content = "这是答案"
    mock_llm.ainvoke.return_value = mock_resp

    answer = await generate_answer("问题", ["上下文1", "上下文2"], mock_llm)
    assert answer == "这是答案"
    mock_llm.ainvoke.assert_awaited()


# ---------------------------------------------------------------------------
# run_eval pipeline (mocked retriever + LLM)
# ---------------------------------------------------------------------------

def test_run_eval_no_llm_pipeline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """End-to-end pipeline with --no-llm: only rule-based metrics, no LLM calls."""
    # Mock retriever: return 1 fake result that matches ground truth
    def fake_retrieve(query, top_k=5, vintage_filter=None):
        from valor.knowledge_base.retriever import ChunkResult
        return [ChunkResult(chunk_id="gt1", doc_id="d1", text="答案文本",
                            doc_title="测试文档", page_no=1)]

    monkeypatch.setattr("valor.knowledge_base.eval_rag.retrieve", fake_retrieve)

    dataset = {
        "version": "1.0",
        "queries": [
            {"id": "q1", "query": "测试问题", "ground_truth_answer": "答案",
             "ground_truth_chunk_ids": ["gt1"], "doc_id": "d1", "query_type": "factual"},
        ],
    }
    ds_path = tmp_path / "dataset.json"
    ds_path.write_text(json.dumps(dataset, ensure_ascii=False), encoding="utf-8")
    out_path = tmp_path / "results.json"

    asyncio.run(run_eval(str(ds_path), str(out_path), no_llm=True))

    out = json.loads(out_path.read_text(encoding="utf-8"))
    assert out["n_queries"] == 1
    assert out["no_llm"] is True
    assert out["summary"]["rule_context_precision"] == 1.0
    assert out["summary"]["rule_context_recall"] == 1.0
    assert out["queries"][0]["retrieved_ids"] == ["gt1"]
    assert out["queries"][0]["answer"] == ""  # no LLM
    assert out["ragas_results"] is None
