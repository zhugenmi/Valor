"""Performance benchmark for single-ticker full-link analysis.

Instruments OpenAICompatProvider.chat to capture latency + token usage
(the stock method discards the `usage` field), runs the full 9-node
LangGraph workflow via stream_analysis(), and emits a structured JSON
report to stdout + writes a copy to perf_results_<ticker>.json.

Usage:
    uv run python scripts/perf_benchmark.py --ticker 600519 --iterations 3

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

import httpx
from loguru import logger

from valor.adapters.llm.openai_compat import OpenAICompatProvider
from valor.agents.workflow import stream_analysis

# ---------------------------------------------------------------------------
# Instrumentation: wrap OpenAICompatProvider.chat to capture usage + latency
# ---------------------------------------------------------------------------

LLM_CALLS: list[dict] = []
_NODE_TIMINGS: list[dict] = []
_ORIGINAL_CHAT = OpenAICompatProvider.chat


async def _instrumented_chat(self, messages, *, model=None, temperature=0.7, max_tokens=4096, **kwargs):
    model_id = model or self.default_model
    payload = {
        "model": model_id,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    payload.update(kwargs)
    url = f"{self.base_url}/chat/completions"
    prompt_chars = sum(len(m.content) for m in messages)

    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=self.timeout) as client:
        resp = await client.post(
            url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        resp.raise_for_status()
        body = resp.json()
    t1 = time.perf_counter()

    content = body["choices"][0]["message"]["content"]
    usage = body.get("usage", {}) or {}

    LLM_CALLS.append({
        "ts": round(t0, 3),
        "model": model_id,
        "latency_s": round(t1 - t0, 3),
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
        "prompt_chars": prompt_chars,
        "completion_chars": len(content),
    })
    return content


OpenAICompatProvider.chat = _instrumented_chat

# Suppress chatty logs
logger.remove()
logger.add(sys.stderr, level="WARNING")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_one(ticker: str, iteration: int) -> dict:
    """Run a single full-link analysis and return its measurement record."""
    LLM_CALLS.clear()
    _NODE_TIMINGS.clear()

    llm_calls_before = len(LLM_CALLS)
    t_start = time.perf_counter()
    wall_start_iso = datetime.now(timezone.utc).isoformat()

    node_order: list[str] = []
    completion_offsets: dict[str, float] = {}

    final_state: dict = {}
    for chunk in stream_analysis(
        ticker=ticker,
        start_date=None,
        end_date=None,
        portfolio={"cash": 100000.0, "stock": 0},
        show_reasoning=False,
        model="auto",
    ):
        for node_name, state_delta in chunk.items():
            now = time.perf_counter()
            if node_name not in completion_offsets:
                completion_offsets[node_name] = round(now - t_start, 3)
                node_order.append(node_name)
            _NODE_TIMINGS.append({
                "node": node_name,
                "completion_offset_s": round(now - t_start, 3),
            })
            # shallow merge for final extraction
            if "messages" in state_delta:
                final_state.setdefault("messages", []).extend(state_delta["messages"])
            if "data" in state_delta:
                final_state.setdefault("data", {}).update(state_delta["data"])

    t_end = time.perf_counter()
    wall_end_iso = datetime.now(timezone.utc).isoformat()

    # Derive phase durations from completion offsets.
    # Graph: market_data -> [5 parallel] -> bull_bear_debate -> risk_manager -> portfolio_manager
    phases: dict[str, float] = {}
    md = completion_offsets.get("market_data", 0.0)
    phases["market_data"] = md
    parallel_nodes = ["technicals", "fundamentals", "valuation", "capital_sentiment", "macro_industry"]
    parallel_max = max((completion_offsets.get(n, 0.0) for n in parallel_nodes), default=0.0)
    phases["parallel_dimensions"] = round(parallel_max - md, 3)
    bd = completion_offsets.get("bull_bear_debate", 0.0)
    phases["bull_bear_debate"] = round(bd - parallel_max, 3)
    rm = completion_offsets.get("risk_manager", 0.0)
    phases["risk_manager"] = round(rm - bd, 3)
    pm = completion_offsets.get("portfolio_manager", 0.0)
    phases["portfolio_manager"] = round(pm - rm, 3)
    phases["_total"] = round(t_end - t_start, 3)

    # Extract final decision (portfolio_management_agent message)
    final_decision = None
    for msg in reversed(final_state.get("messages", [])):
        if getattr(msg, "name", None) == "portfolio_management_agent":
            try:
                final_decision = json.loads(msg.content)
            except Exception:
                final_decision = {"raw": str(getattr(msg, "content", ""))[:200]}
            break

    return {
        "iteration": iteration,
        "ticker": ticker,
        "wall_start_iso": wall_start_iso,
        "wall_end_iso": wall_end_iso,
        "total_wall_s": round(t_end - t_start, 3),
        "node_order": node_order,
        "completion_offsets": completion_offsets,
        "phases_s": phases,
        "llm_calls": list(LLM_CALLS[llm_calls_before:]),
        "llm_call_count": len(LLM_CALLS[llm_calls_before:]),
        "final_decision": final_decision,
    }


def summarize(records: list[dict]) -> dict:
    """Aggregate per-iteration records into a summary."""
    n = len(records)
    total_walls = [r["total_wall_s"] for r in records]
    llm_counts = [r["llm_call_count"] for r in records]
    all_calls = [c for r in records for c in r["llm_calls"]]
    prompt_tokens = [c["prompt_tokens"] for c in all_calls]
    completion_tokens = [c["completion_tokens"] for c in all_calls]
    total_tokens = [c["total_tokens"] for c in all_calls]
    latencies = [c["latency_s"] for c in all_calls]

    def stats(arr):
        if not arr:
            return {"count": 0}
        return {
            "count": len(arr),
            "sum": round(sum(arr), 1),
            "mean": round(sum(arr) / len(arr), 2),
            "min": round(min(arr), 2),
            "max": round(max(arr), 2),
            "p50": round(sorted(arr)[len(arr) // 2], 2),
        }

    return {
        "iterations": n,
        "total_wall_s": stats(total_walls),
        "llm_calls_per_run": stats(llm_counts),
        "llm_latency_s": stats(latencies),
        "prompt_tokens": stats(prompt_tokens),
        "completion_tokens": stats(completion_tokens),
        "total_tokens": stats(total_tokens),
        "total_tokens_per_run": round(sum(total_tokens) / n, 1) if n else 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="perf_benchmark")
    parser.add_argument("--ticker", default="600519", help="A-share ticker code")
    parser.add_argument("--iterations", type=int, default=3, help="Repeat count")
    parser.add_argument("--output", default="", help="Optional output JSON path")
    args = parser.parse_args(argv)

    provider = OpenAICompatProvider()
    print(f"[perf] provider={provider.provider_name} base_url={provider.base_url} model={provider.default_model}")
    print(f"[perf] ticker={args.ticker} iterations={args.iterations}")

    records: list[dict] = []
    for i in range(1, args.iterations + 1):
        print(f"\n[perf] === iteration {i}/{args.iterations} ===")
        rec = run_one(args.ticker, i)
        records.append(rec)
        print(
            f"[perf] iter {i}: wall={rec['total_wall_s']}s  "
            f"llm_calls={rec['llm_call_count']}  "
            f"tokens={sum(c['total_tokens'] for c in rec['llm_calls'])}  "
            f"nodes={len(rec['node_order'])}"
        )
        for phase, dur in rec["phases_s"].items():
            if phase == "_total":
                continue
            print(f"    phase {phase:<20} {dur}s")
        for c in rec["llm_calls"]:
            print(
                f"    llm  ptok={c['prompt_tokens']:>5} ctok={c['completion_tokens']:>4} "
                f"lat={c['latency_s']}s"
            )

    summary = summarize(records)
    print("\n[perf] === SUMMARY ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ticker": args.ticker,
        "provider": {
            "name": provider.provider_name,
            "base_url": provider.base_url,
            "model": provider.default_model,
        },
        "summary": summary,
        "records": records,
    }
    out_path = args.output or f"perf_results_{args.ticker}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n[perf] full report -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
