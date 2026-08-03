"""API endpoint response-time benchmark.

Tests:
  1. GET /healthz                 - trivial baseline (no LLM, no data)
  2. GET /api/v1/system/default-tickers - static data baseline
  3. POST /api/v1/agents/stream   - SSE streaming full workflow
     (first-byte time, total stream time, event count, final decision)

Usage:
    # Start server first:
    uv run uvicorn valor.server.main:app --port 8000 &
    uv run python scripts/perf_api.py --ticker 600519 --sse

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from datetime import datetime, timezone

import httpx

BASE = "http://127.0.0.1:8000"


def fmt_stats(arr: list[float]) -> dict:
    if not arr:
        return {"count": 0}
    s = sorted(arr)
    return {
        "count": len(s),
        "mean_ms": round(sum(s) / len(s), 1),
        "min_ms": round(s[0], 1),
        "max_ms": round(s[-1], 1),
        "p50_ms": round(s[len(s) // 2], 1),
        "p95_ms": round(s[int(len(s) * 0.95)] if len(s) > 1 else s[0], 1),
    }


async def test_lightweight() -> dict:
    """Hit /healthz and /api/v1/system/default-tickers N times, report latency."""
    results: dict = {"healthz": [], "default_tickers": []}
    async with httpx.AsyncClient(timeout=10) as client:
        for _ in range(20):
            t0 = time.perf_counter()
            r = await client.get(f"{BASE}/healthz")
            t1 = time.perf_counter()
            assert r.status_code == 200, f"healthz: {r.status_code}"
            results["healthz"].append((t1 - t0) * 1000)

        for _ in range(20):
            t0 = time.perf_counter()
            r = await client.get(f"{BASE}/api/v1/system/default-tickers?language=zh")
            t1 = time.perf_counter()
            assert r.status_code == 200, f"default-tickers: {r.status_code}"
            results["default_tickers"].append((t1 - t0) * 1000)

    return {
        "healthz_ms": fmt_stats(results["healthz"]),
        "default_tickers_ms": fmt_stats(results["default_tickers"]),
    }


async def test_sse(ticker: str) -> dict:
    """POST /api/v1/agents/stream, measure first-byte + total + events."""
    payload = {
        "query": f"分析 {ticker}",
        "agent_name": "ValorAgent",
        "ticker": ticker,
    }
    t_start = time.perf_counter()
    first_byte_s: float | None = None
    event_counts: dict[str, int] = {}
    final_decision = None
    event_types_in_order: list[str] = []
    total_bytes = 0

    async with httpx.AsyncClient(timeout=900) as client:
        async with client.stream(
            "POST", f"{BASE}/api/v1/agents/stream", json=payload
        ) as resp:
            status = resp.status_code
            buf = b""
            async for chunk in resp.aiter_bytes():
                if first_byte_s is None and chunk:
                    first_byte_s = round(time.perf_counter() - t_start, 3)
                total_bytes += len(chunk)
                buf += chunk
                while b"\n\n" in buf:
                    raw, buf = buf.split(b"\n\n", 1)
                    line = raw.strip()
                    if not line.startswith(b"data: "):
                        continue
                    try:
                        evt = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue
                    etype = evt.get("event", "")
                    event_types_in_order.append(etype)
                    event_counts[etype] = event_counts.get(etype, 0) + 1
                    if etype == "workflow_completed":
                        final_decision = evt.get("data", {}).get("final_decision")
                    if etype == "done":
                        pass
    t_end = time.perf_counter()
    return {
        "ticker": ticker,
        "http_status": status,
        "first_byte_s": first_byte_s,
        "total_stream_s": round(t_end - t_start, 3),
        "total_bytes": total_bytes,
        "event_count": sum(event_counts.values()),
        "event_counts": event_counts,
        "event_types_in_order": event_types_in_order,
        "final_decision": final_decision,
    }


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="perf_api")
    parser.add_argument("--ticker", default="600519")
    parser.add_argument("--sse", action="store_true", help="Also run SSE test (~6 min)")
    parser.add_argument("--output", default="perf_api_results.json")
    args = parser.parse_args(argv)

    print(f"[api] base={BASE}  ticker={args.ticker}  sse={args.sse}")

    # 0. connectivity check
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            r = await client.get(f"{BASE}/healthz")
            print(f"[api] connectivity: {r.status_code} {r.json()}")
        except Exception as e:
            print(f"[api] server not reachable: {e}")
            return 1

    out: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": BASE,
        "ticker": args.ticker,
    }

    print("[api] testing lightweight endpoints (20 hits each)...")
    out["lightweight"] = await test_lightweight()
    print(json.dumps(out["lightweight"], ensure_ascii=False, indent=2))

    if args.sse:
        print(f"\n[api] testing SSE stream for {args.ticker} (this takes ~6 min)...")
        sse_result = await test_sse(args.ticker)
        out["sse"] = sse_result
        print(json.dumps(sse_result, ensure_ascii=False, indent=2, default=str))

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n[api] full report -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
