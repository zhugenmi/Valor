"""CSV import for portfolios. License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial."""
from __future__ import annotations
import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal
from pydantic import BaseModel
from valor.portfolio.models import Holding, Lot
from valor.portfolio.storage import gen_lot_id

class ImportRowError(BaseModel):
    row: int
    reason: str

class ImportResult(BaseModel):
    holdings: list[Holding]
    errors: list[ImportRowError]
    format: str
    total_rows: int
    imported_rows: int

def _parse_decimal(s: str) -> Decimal:
    return Decimal(s.replace(",", "").strip())

def _parse_int(s: str) -> int:
    return int(s.replace(",", "").strip())

def _normalize_header(h: str) -> str:
    return h.strip().lower()

def _merge_extra_fields(fields: list[str], num_headers: int) -> list[str]:
    """When CSV parsing yields more fields than headers, try merging adjacent
    fields that were split by an unquoted thousands-separator comma.
    Only merges when the left part is 1–3 digits and the right part is exactly
    3 digits — the classic pattern of a thousands-separator split."""
    if len(fields) <= num_headers:
        return fields
    merged = list(fields)
    while len(merged) > num_headers:
        best = -1
        for i in range(len(merged) - 1):
            left = merged[i].strip()
            right = merged[i + 1].strip()
            if not (left.isdigit() and 1 <= len(left) <= 3
                    and right.isdigit() and len(right) == 3):
                continue
            candidate = left + right
            try:
                Decimal(candidate)
                best = i
                break
            except Exception:
                continue
        if best < 0:
            break  # cannot merge further
        merged[best] = merged[best] + merged[best + 1]
        merged.pop(best + 1)
    return merged[:num_headers]

def parse_generic_csv(content: bytes, encoding: str = "utf-8") -> list[Holding]:
    text = content.decode(encoding)
    reader = csv.reader(io.StringIO(text))
    raw_headers = next(reader, None)
    if raw_headers is None:
        return []
    fieldnames = [_normalize_header(h) for h in raw_headers]
    holdings: list[Holding] = []
    for i, raw_row in enumerate(reader, start=2):
        if not raw_row or not any(raw_row):
            continue
        fields = _merge_extra_fields(raw_row, len(fieldnames))
        row = dict(zip(fieldnames, fields))
        try:
            ticker = row["ticker"].strip().zfill(6)
            qty = _parse_int(row["quantity"])
            cost = _parse_decimal(row["cost_price"])
            name = row.get("name") or None
            open_date_str = row.get("open_date")
            open_date = date.fromisoformat(open_date_str) if open_date_str else date.today()
            fees_str = row.get("fees")
            fees = _parse_decimal(fees_str) if fees_str else Decimal("0")
            lot = Lot(lot_id=gen_lot_id(), open_date=open_date, quantity=qty,
                      cost_price=cost, fees=fees)
            holdings.append(Holding(ticker=ticker, name=name, lots=[lot]))
        except (KeyError, ValueError, InvalidOperation):
            continue
    return holdings


_EASTMONEY_HEADER_MAP = {
    "证券代码": "ticker",
    "证券名称": "name",
    "持仓数量": "quantity",
    "成本价": "cost_price",
}


def detect_format(content: bytes) -> Literal["generic", "eastmoney", "unknown"]:
    for enc in ("utf-8", "gbk"):
        try:
            text = content.decode(enc)
        except UnicodeDecodeError:
            continue
        if "证券代码" in text or "成本价" in text:
            return "eastmoney"
        if "ticker" in text.lower():
            return "generic"
    return "unknown"


def parse_eastmoney_csv(content: bytes) -> list[Holding]:
    text = content.decode("gbk")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return []
    header = [_normalize_header_cn(h) for h in rows[0]]
    col_map = {v: i for i, v in enumerate(header) if v in _EASTMONEY_HEADER_MAP.values()}
    holdings: list[Holding] = []
    for raw_row in rows[1:]:
        if not raw_row or "合计" in raw_row[0]:
            continue
        row = _merge_extra_fields(raw_row, len(header))
        try:
            ticker = row[col_map["ticker"]].strip().zfill(6)
            name = row[col_map["name"]].strip()
            qty = _parse_int(row[col_map["quantity"]])
            cost = _parse_decimal(row[col_map["cost_price"]])
            lot = Lot(lot_id=gen_lot_id(), open_date=date.today(), quantity=qty, cost_price=cost)
            holdings.append(Holding(ticker=ticker, name=name, lots=[lot]))
        except (KeyError, ValueError, InvalidOperation, IndexError):
            continue
    return holdings


def _normalize_header_cn(h: str) -> str:
    h = h.strip()
    return _EASTMONEY_HEADER_MAP.get(h, h)
