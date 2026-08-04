"""Document parser: PDF -> ParsedDocument (Word/Excel/TXT/MD in Task 2.2).

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber


@dataclass
class ParsedPage:
    page_no: int
    text: str


@dataclass
class ParsedTable:
    page_no: int
    rows: list[list[str]]
    caption: str | None = None


@dataclass
class HeadingNode:
    level: int
    text: str
    page_no: int
    children: list["HeadingNode"] = field(default_factory=list)


@dataclass
class ParsedDocument:
    file_path: str
    mime_type: str
    pages: list[ParsedPage] = field(default_factory=list)
    tables: list[ParsedTable] = field(default_factory=list)
    heading_tree: list[HeadingNode] = field(default_factory=list)
    full_text: str = ""


def parse(file_path: Path, mime_type: str) -> ParsedDocument:
    """Dispatch parser by mime_type."""
    if mime_type == "application/pdf":
        return parse_pdf(file_path)
    raise NotImplementedError(f"Task 2.2 will implement {mime_type} parsing")


def parse_pdf(file_path: Path) -> ParsedDocument:
    """Parse PDF with pdfplumber: extract text + tables per page."""
    doc = ParsedDocument(file_path=str(file_path), mime_type="application/pdf")
    text_parts: list[str] = []
    with pdfplumber.open(file_path) as pdf:
        for idx, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""
            doc.pages.append(ParsedPage(page_no=idx, text=page_text))
            text_parts.append(page_text)
            # Extract tables
            for tbl in page.extract_tables() or []:
                doc.tables.append(ParsedTable(page_no=idx, rows=tbl))
            # Heading heuristic: chars with size >= 14 and line length <= 30
            _extract_headings_from_page(page, idx, doc.heading_tree)
    doc.full_text = "\n\n".join(text_parts)
    return doc


def _extract_headings_from_page(page, page_no: int, tree: list[HeadingNode]) -> None:
    """Heuristic: lines with font size >= 14 and char count <= 30 are headings."""
    try:
        words = page.extract_words(extra_attrs=["size"])
    except Exception:
        return
    # Group words by line (y0 rounded)
    lines: dict[float, list[dict]] = {}
    for w in words:
        key = round(w.get("top", 0), 0)
        lines.setdefault(key, []).append(w)
    for y in sorted(lines.keys()):
        words_in_line = sorted(lines[y], key=lambda w: w.get("x0", 0))
        text = "".join(w.get("text", "") for w in words_in_line).strip()
        if not text or len(text) > 30:
            continue
        avg_size = sum(w.get("size", 0) for w in words_in_line) / len(words_in_line)
        if avg_size >= 14:
            tree.append(HeadingNode(level=1, text=text, page_no=page_no))