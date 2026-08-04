"""Prompt file loader - loads Markdown prompt templates from the prompts/ directory.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

import re as _re
from pathlib import Path
from typing import Any

_BASE_DIR = Path(__file__).resolve().parents[2]


def load_prompt(relative_path: str) -> str:
    """Load a prompt file as a string, substituting {{name}} includes with prompts/_shared/{name}.md.

    Args:
        relative_path: Path relative to project root, e.g. "prompts/sentiment/system.md"
    """
    path = _BASE_DIR / relative_path
    text = path.read_text(encoding="utf-8")

    def _include(match):
        name = match.group(1)
        shared_path = _BASE_DIR / f"prompts/_shared/{name}.md"
        if shared_path.exists():
            return shared_path.read_text(encoding="utf-8")
        return match.group(0)

    return _re.sub(r"\{\{(\w+)\}\}", _include, text)


def format_prompt(relative_path: str, **kwargs: Any) -> str:
    """Load a prompt file and format it with keyword arguments."""
    template = load_prompt(relative_path)
    return template.format(**kwargs)
