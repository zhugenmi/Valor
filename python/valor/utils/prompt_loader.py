"""Prompt file loader - loads Markdown prompt templates from the prompts/ directory.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from pathlib import Path
from typing import Any

_BASE_DIR = Path(__file__).resolve().parents[2]


def load_prompt(relative_path: str) -> str:
    """Load a prompt file as a string.

    Args:
        relative_path: Path relative to project root, e.g. "prompts/sentiment/system.md"
    """
    path = _BASE_DIR / relative_path
    return path.read_text(encoding="utf-8")


def format_prompt(relative_path: str, **kwargs: Any) -> str:
    """Load a prompt file and format it with keyword arguments."""
    template = load_prompt(relative_path)
    return template.format(**kwargs)
