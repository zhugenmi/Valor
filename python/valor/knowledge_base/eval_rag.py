"""RAG evaluation script using ragas.

Runs 4 metrics:
- faithfulness: answer grounded on context (LLM-based)
- answer_relevancy: answer responds to query (LLM + embeddings)
- context_precision: retrieved chunks vs ground truth (LLM-based, ragas version)
- context_recall: ground truth chunks retrieved (LLM-based, ragas version)

Also computes rule-based context_precision/recall (exact chunk_id match) as a
sanity check that doesn't depend on LLM.

CLI:
    uv run python -m valor.knowledge_base.eval_rag \
        --dataset tests/data/rag_eval_dataset.json \
        --output tests/data/rag_eval_results.json \
        [--no-llm]

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
from __future__ import annotations

# --- ragas 0.4.x compat shim ----------------------------------------------
# ragas 0.4.3 imports `langchain_community.chat_models.vertexai.ChatVertexAI`
# unconditionally at module load, but langchain_community 0.4.2 removed that
# path (moved to langchain-google-vertexai). Inject a stub so import succeeds.
import sys
from unittest.mock import MagicMock
sys.modules.setdefault("langchain_community.chat_models.vertexai", MagicMock())
# --------------------------------------------------------------------------

import argparse
import asyncio
import json
import os
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=DeprecationWarning)

from dotenv import load_dotenv

load_dotenv()

# NOTE: langchain_openai.ChatOpenAI and ragas are imported lazily inside
# run_eval() so that --no-llm mode (rule-based metrics only) works without
# those optional dev deps being installed.
from langchain_core.embeddings import Embeddings

from valor.knowledge_base.embedder import get_embedder
from valor.knowledge_base.retriever import retrieve

METRICS = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]


class BgeEmbeddings(Embeddings):
    """Wrap project's bge-small-zh-v1.5 embedder as a LangChain Embeddings.

    Used by ragas for answer_relevancy (which needs query/response embeddings).
    """

    def __init__(self) -> None:
        self._embedder = get_embedder()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embedder.embed_batch(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embedder.embed(text)


ANSWER_GEN_PROMPT = """你是一名金融分析助手。请基于以下检索到的上下文回答用户问题。

要求:
1. 只使用上下文中的信息,不要编造
2. 回答简洁准确,包含关键数字/日期/名称
3. 如果上下文不足以回答,请说明"上下文中无足够信息"
4. 在回答末尾标注来源,如 [来源:文档名,页码]

上下文:
{context}

问题: {query}

回答:"""


async def generate_answer(query: str, contexts: list[str], llm) -> str:
    """Generate answer using LLM with retrieved context. llm is a ChatOpenAI-like object."""
    prompt = ANSWER_GEN_PROMPT.format(
        context="\n\n---\n\n".join(contexts) if contexts else "(无检索结果)",
        query=query,
    )
    resp = await llm.ainvoke(prompt)
    return resp.content if hasattr(resp, "content") else str(resp)


def rule_context_metrics(retrieved_ids: list[str], gt_ids: list[str]) -> tuple[float, float]:
    """Exact-match precision/recall (rule-based, no LLM)."""
    retrieved_set = set(retrieved_ids)
    gt_set = set(gt_ids)
    if not retrieved_set:
        return 0.0, 0.0
    overlap = retrieved_set & gt_set
    precision = len(overlap) / len(retrieved_set)
    recall = len(overlap) / max(len(gt_set), 1)
    return precision, recall


async def run_eval(dataset_path: str, output_path: str, no_llm: bool = False) -> None:
    """Run full evaluation pipeline."""
    # Ensure KB is initialized (loads sqlite-vec extension, creates tables)
    from valor.server import db
    if not db.KB_AVAILABLE:
        db.init_db()
    if not db.KB_AVAILABLE:
        raise RuntimeError("sqlite-vec not available; KB cannot be queried")

    dataset = json.loads(Path(dataset_path).read_text(encoding="utf-8"))
    queries = dataset["queries"]
    print(f"Loaded {len(queries)} queries from {dataset_path}")

    # Init LLM (skip if --no-llm)
    llm = None
    if not no_llm:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model=os.getenv("VALOR_OPENAI_MODEL", "gpt-4o"),
            openai_api_key=os.getenv("VALOR_OPENAI_API_KEY", ""),
            openai_api_base=os.getenv("VALOR_OPENAI_BASE_URL", ""),
            temperature=0,
            max_tokens=1024,
        )

    # Build per-query results
    samples = []
    for i, q in enumerate(queries):
        t0 = time.time()
        try:
            results = retrieve(q["query"], top_k=5)
        except Exception as exc:
            print(f"  [{i+1}/{len(queries)}] retrieve FAILED: {exc}")
            results = []
        latency_ms = (time.time() - t0) * 1000

        retrieved_contexts = [r.text for r in results]
        retrieved_ids = [r.chunk_id for r in results]
        retrieved_titles = [r.doc_title for r in results]

        # Rule-based retrieval metrics
        rule_p, rule_r = rule_context_metrics(retrieved_ids, q["ground_truth_chunk_ids"])

        # LLM answer
        answer = ""
        llm_error = None
        if not no_llm:
            try:
                answer = await generate_answer(q["query"], retrieved_contexts, llm)
            except Exception as exc:
                llm_error = str(exc)
                answer = f"[LLM_ERROR] {exc}"

        samples.append({
            "id": q["id"],
            "query": q["query"],
            "query_type": q.get("query_type", "factual"),
            "doc_id": q["doc_id"],
            "retrieved_ids": retrieved_ids,
            "retrieved_titles": retrieved_titles,
            "retrieved_contexts": retrieved_contexts,
            "ground_truth": q["ground_truth_answer"],
            "ground_truth_chunk_ids": q["ground_truth_chunk_ids"],
            "answer": answer,
            "llm_error": llm_error,
            "latency_ms": round(latency_ms, 1),
            "rule_context_precision": round(rule_p, 4),
            "rule_context_recall": round(rule_r, 4),
        })
        status = f"rule_p={rule_p:.2f} rule_r={rule_r:.2f} lat={latency_ms:.0f}ms"
        if not no_llm:
            status += f" ans_len={len(answer)}"
        print(f"  [{i+1}/{len(queries)}] {q['id']} {status}")

    # Run ragas if LLM enabled and we have answers
    ragas_results = None
    ragas_summary = None
    if not no_llm and llm is not None:
        print("\nRunning ragas evaluation (4 metrics)...")
        try:
            from ragas import evaluate
            from ragas.dataset_schema import EvaluationDataset, SingleTurnSample
            from ragas.metrics import context_precision, context_recall, faithfulness
            from ragas.metrics._answer_relevance import answer_relevancy

            ragas_samples = [
                SingleTurnSample(
                    user_input=s["query"],
                    response=s["answer"],
                    retrieved_contexts=s["retrieved_contexts"],
                    reference=s["ground_truth"],
                )
                for s in samples
                if not s.get("llm_error")
            ]
            eval_dataset = EvaluationDataset(ragas_samples)
            embeddings = BgeEmbeddings()

            result = evaluate(
                dataset=eval_dataset,
                metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
                llm=llm,
                embeddings=embeddings,
                show_progress=True,
                raise_exceptions=False,
            )
            # result is EvaluationResult; convert to dict
            df = result.to_pandas()
            ragas_results = df.to_dict(orient="records")
            # summary: mean of each metric
            metric_cols = [c for c in df.columns if c in METRICS]
            ragas_summary = {c: float(df[c].mean()) for c in metric_cols}
            print(f"  ragas summary: {ragas_summary}")
        except Exception as exc:
            print(f"  ragas evaluation FAILED: {exc}")
            ragas_results = [{"error": str(exc)}]
            ragas_summary = {"error": str(exc)}

    # Build output
    rule_p_mean = sum(s["rule_context_precision"] for s in samples) / max(len(samples), 1)
    rule_r_mean = sum(s["rule_context_recall"] for s in samples) / max(len(samples), 1)
    lat_mean = sum(s["latency_ms"] for s in samples) / max(len(samples), 1)

    output = {
        "version": "1.0",
        "created": "2026-08-04",
        "dataset_path": str(dataset_path),
        "n_queries": len(samples),
        "no_llm": no_llm,
        "summary": {
            "rule_context_precision": round(rule_p_mean, 4),
            "rule_context_recall": round(rule_r_mean, 4),
            "mean_latency_ms": round(lat_mean, 1),
            **(ragas_summary or {}),
        },
        "queries": samples,
        "ragas_results": ragas_results,
    }

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nResults saved to {output_path}")
    print(f"Summary: {json.dumps(output['summary'], ensure_ascii=False)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG evaluation using ragas")
    parser.add_argument("--dataset", required=True, help="Path to rag_eval_dataset.json")
    parser.add_argument("--output", required=True, help="Path to output results JSON")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM-based metrics (rule-only)")
    args = parser.parse_args()
    asyncio.run(run_eval(args.dataset, args.output, args.no_llm))


if __name__ == "__main__":
    main()
