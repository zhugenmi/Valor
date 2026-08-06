"""LLM-based query rewriter for agentic RAG.

Generates N semantically-equivalent reformulations of a user query
(synonym expansion, term normalization) to improve retrieval recall.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
from __future__ import annotations

import asyncio
import os
import re
import threading
from typing import Any

from valor.adapters.llm import get_llm_provider
from valor.core.protocols import Message

# Module-level cache: query -> list[str]. Bounded to 1000 entries (LRU not implemented;
# simple dict, cleared on process restart). Avoids re-rewriting identical queries.
_CACHE: dict[str, list[str]] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_MAX = 1000

_REWRITE_PROMPT = """你是一名金融信息检索专家。请将用户查询重写为 {n} 个语义等价但表达不同的版本,用于提升检索召回率。

要求:
1. 同义词扩展:如"营收" -> "营业收入/营业总收入"
2. 术语规范化:如"茅台" -> "贵州茅台"
3. 保留关键实体(公司名、指标名、年份)
4. 每行一个重写,以 "1. " "2. " 等数字前缀开头
5. 不要解释,只输出重写后的查询

用户查询: {query}

重写({n} 条):"""


def _parse_rewrites(raw: str, original: str, n: int) -> list[str]:
    """Parse LLM response into a list of n rewritten queries.

    Strips numeric prefixes ("1. ", "2. "), filters empty, dedups, and pads
    with the original query if the LLM returned fewer than n.
    """
    if not raw:
        return [original]
    lines = [ln.strip() for ln in raw.strip().splitlines() if ln.strip()]
    # Strip leading "1. " / "1、" / "1)" prefixes
    cleaned: list[str] = []
    for ln in lines:
        m = re.match(r"^\d+[.、)]\s*(.+)$", ln)
        cleaned.append(m.group(1).strip() if m else ln)
    # Dedup while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for q in cleaned:
        if q and q not in seen:
            seen.add(q)
            unique.append(q)
    # Pad with original if short
    while len(unique) < n:
        unique.append(original)
    return unique[:n]


def _run_async(coro: Any) -> Any:
    """Run an async coroutine from sync context.

    Handles two cases:
    1. No running event loop -> asyncio.run()
    2. Running loop (e.g., inside FastAPI route) -> new thread + new loop

    Case 2 is rare for retrieve() which is sync, but defensive.
    """
    try:
        asyncio.get_running_loop()  # raises RuntimeError if no loop
    except RuntimeError:
        return asyncio.run(coro)
    # Running loop exists: run in a separate thread to avoid nested-loop error
    result: list[Any] = []
    err: list[Exception] = []

    def _worker() -> None:
        try:
            new_loop = asyncio.new_event_loop()
            try:
                result.append(new_loop.run_until_complete(coro))
            finally:
                new_loop.close()
        except Exception as e:
            err.append(e)

    t = threading.Thread(target=_worker)
    t.start()
    t.join()
    if err:
        raise err[0]
    return result[0] if result else None


async def _call_llm(query: str, n: int) -> str:
    """Call LLM provider to rewrite query. Returns raw response text."""
    provider = get_llm_provider()
    prompt = _REWRITE_PROMPT.format(n=n, query=query)
    messages = [Message(role="user", content=prompt)]
    resp = await provider.chat(messages, temperature=0.3, max_tokens=512)
    return resp


def rewrite_query(query: str, n: int = 3) -> list[str]:
    """Rewrite a query into n equivalent variants.

    Returns a list of n strings (including the original as one variant).
    Falls back to [query] if LLM is disabled or fails.

    Caching: identical (query, n) pairs reuse the cached result.
    """
    if os.getenv("VALOR_KB_QUERY_REWRITE", "1") != "1":
        return [query]

    cache_key = f"{query}::{n}"
    with _CACHE_LOCK:
        if cache_key in _CACHE:
            return _CACHE[cache_key]

    try:
        raw = _run_async(_call_llm(query, n))
        rewrites = _parse_rewrites(raw, original=query, n=n)
        # Ensure original is included
        if query not in rewrites:
            rewrites = [query] + rewrites[: n - 1]
    except Exception:
        # LLM failure: degrade gracefully
        rewrites = [query]

    with _CACHE_LOCK:
        if len(_CACHE) >= _CACHE_MAX:
            # Evict ~10% arbitrarily (not true LRU, but bounds memory)
            keys = list(_CACHE.keys())
            for k in keys[: max(1, _CACHE_MAX // 10)]:
                _CACHE.pop(k, None)
        _CACHE[cache_key] = rewrites
    return rewrites