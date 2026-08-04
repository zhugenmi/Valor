"""Financial fact extraction + correction. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations

import re

from valor.knowledge_base.constants import FIELD_ALIASES
from valor.knowledge_base.models import FinancialFact
from valor.knowledge_base.parser import ParsedDocument


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
