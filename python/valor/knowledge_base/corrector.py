"""Financial fact extraction + correction. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re

from valor.knowledge_base.constants import FIELD_ALIASES
from valor.knowledge_base.models import FinancialFact
from valor.knowledge_base.parser import ParsedDocument


_logger = logging.getLogger(__name__)


_ALIAS_TO_FIELD: dict[str, str] = {}
for _field, _aliases in FIELD_ALIASES.items():
    for _alias in _aliases:
        _ALIAS_TO_FIELD[_alias] = _field


_UNIT_PATTERNS = [
    (re.compile(r"单位[：:]\s*亿元"), "亿元"),
    (re.compile(r"单位[：:]\s*万元"), "万元"),
    (re.compile(r"单位[：:]\s*元"), "元"),
]


def _detect_unit(text: str) -> str | None:
    for pat, unit in _UNIT_PATTERNS:
        if pat.search(text):
            return unit
    return None


def _parse_number(s: str) -> float | None:
    """Parse a numeric string like '1,238.45' or '15.3%'."""
    s = s.strip().replace(",", "").replace("%", "")
    try:
        return float(s)
    except ValueError:
        return None


def _match_field(cell: str) -> str | None:
    """Match a cell against FIELD_ALIASES. Returns field_name or None."""
    cell_clean = cell.strip()
    if cell_clean in _ALIAS_TO_FIELD:
        return _ALIAS_TO_FIELD[cell_clean]
    for alias, field in _ALIAS_TO_FIELD.items():
        if alias in cell_clean:
            return field
    return None


def extract_financial_facts(
    parsed: ParsedDocument,
    ticker: str,
    report_period: str,
) -> list[FinancialFact]:
    """Extract financial facts from parsed tables. MVP: 9 fields."""
    facts: list[FinancialFact] = []
    seen: set[str] = set()

    for tbl in parsed.tables:
        if not tbl.rows:
            continue
        unit = _detect_unit(tbl.caption or "") or _detect_unit(parsed.full_text[:200])

        header = tbl.rows[0]
        current_col = 1
        for i, h in enumerate(header):
            if any(kw in h for kw in ["本期", "本报告期", "报告期", "本期金额"]):
                current_col = i
                break

        for row in tbl.rows[1:]:
            if not row:
                continue
            label = row[0] if len(row) > 0 else ""
            field_name = _match_field(label)
            if not field_name or field_name in seen:
                continue
            if current_col >= len(row):
                continue
            value = _parse_number(row[current_col])
            if value is None:
                continue
            facts.append(FinancialFact(
                ticker=ticker,
                report_period=report_period,
                field_name=field_name,
                value=value,
                unit=unit,
                source_page=tbl.page_no,
            ))
            seen.add(field_name)

    return facts


# ---------------------------------------------------------------------------
# verify_and_correct
# ---------------------------------------------------------------------------

def _normalize_cached(df_or_dict: object) -> dict[str, float]:
    """Normalize DataRouter return (DataFrame or dict) to {field_name: value}.

    DataRouter.get_financial_indicators returns a DataFrame with akshare-native
    Chinese column names. We take the latest row (iloc[0]) and map columns to
    our field_name keys via FIELD_ALIASES contains-match.
    """
    if df_or_dict is None:
        return {}
    if isinstance(df_or_dict, dict):
        out: dict[str, float] = {}
        for k, v in df_or_dict.items():
            if v is None:
                continue
            try:
                out[k] = float(v)
            except (ValueError, TypeError):
                continue
        return out
    try:
        import pandas as pd  # noqa: PLC0415
        if isinstance(df_or_dict, pd.DataFrame) and not df_or_dict.empty:
            row = df_or_dict.iloc[0]
            result: dict[str, float] = {}
            for col in df_or_dict.columns:
                val = row[col]
                if pd.isna(val):
                    continue
                field = _match_field(str(col))
                if field and field not in result:
                    try:
                        result[field] = float(val)
                    except (ValueError, TypeError):
                        pass
            return result
    except Exception as exc:
        _logger.debug("normalize_cached failed: %s", exc)
    return {}


def verify_and_correct_for_doc(doc_id: str, parsed: ParsedDocument) -> int:
    """Verify extracted facts against DataRouter cache, write corrections for diffs.

    Called by indexer after chunking. Returns the number of corrections written.
    """
    from valor.knowledge_base.kb_store import get_document, insert_correction
    from valor.knowledge_base.parser import extract_report_period, extract_ticker

    doc = get_document(doc_id)
    if doc is None or doc.category != "disclosure":
        return 0

    meta = json.loads(doc.meta_json) if doc.meta_json else {}
    if not meta.get("enable_correction", True):
        return 0

    ticker = doc.ticker or extract_ticker(parsed)
    report_period = meta.get("report_period") or extract_report_period(parsed)
    if not ticker or not report_period:
        return 0

    facts = extract_financial_facts(parsed, ticker, report_period)
    if not facts:
        return 0

    cached: dict[str, float] = {}
    try:
        from valor.adapters.data.factory import build_data_router
        router = build_data_router()
        raw = asyncio.run(router.get_financial_indicators(ticker))
        cached = _normalize_cached(raw)
    except Exception as exc:
        _logger.warning("failed to fetch cached financials for %s: %s", ticker, exc)
        cached = {}

    tolerance = float(os.getenv("VALOR_KB_CORRECTION_TOLERANCE", "0.01"))
    count = 0
    for fact in facts:
        cached_val = cached.get(fact.field_name)
        if cached_val is None:
            insert_correction(
                ticker=ticker, report_period=report_period, field_name=fact.field_name,
                original_value=None, corrected_value=str(fact.value), unit=fact.unit,
                source_doc_id=doc_id, source_page=fact.source_page,
            )
            count += 1
            continue
        diff = abs(fact.value - cached_val) / max(abs(cached_val), 1e-9)
        if diff > tolerance:
            insert_correction(
                ticker=ticker, report_period=report_period, field_name=fact.field_name,
                original_value=str(cached_val), corrected_value=str(fact.value),
                unit=fact.unit, source_doc_id=doc_id, source_page=fact.source_page,
            )
            count += 1
    return count


def get_corrections(ticker: str, report_period: str):
    """Proxy to kb_store.get_corrections for re-export."""
    from valor.knowledge_base.kb_store import get_corrections as _get
    return _get(ticker, report_period)
