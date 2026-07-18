"""Tests for the prompt_loader module."""


from valor.utils.prompt_loader import _BASE_DIR, load_prompt, format_prompt


def test_base_dir_resolves():
    """_BASE_DIR should resolve to a real directory."""
    assert _BASE_DIR.exists()
    assert _BASE_DIR.is_dir()


def test_load_prompt_known_file():
    """load_prompt should load a known prompt file."""
    content = load_prompt("prompts/capital_sentiment/system.md")
    assert isinstance(content, str)
    assert len(content) > 0


def test_load_prompt_nonexistent():
    """load_prompt should raise FileNotFoundError for missing file."""
    import pytest

    with pytest.raises(FileNotFoundError):
        load_prompt("prompts/nonexistent/file.md")


def test_format_prompt():
    """format_prompt should substitute template variables."""
    result = format_prompt("prompts/news_query_builder/user.md", symbol="000001", agent_name="test", date="2024-01-01")
    assert isinstance(result, str)
    assert len(result) > 0
