"""End-to-end smoke tests: CLI argument parsing and mocked adapter output."""

from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

from valor.cli.main import main


def test_cli_requires_ticker():
    """Missing --ticker should exit with code 2 (argparse error)."""
    with pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code == 2


def test_cli_smoke_600519(capsys):
    """Run CLI for 600519 with mocked adapter; verify output contains ticker."""
    fake_router = AsyncMock()
    fake_router.get_realtime_quote.return_value = pd.DataFrame(
        {
            "代码": ["600519"],
            "名称": ["贵州茅台"],
            "最新价": [1500.0],
            "涨跌幅": [1.23],
        }
    )

    with patch("valor.cli.main.get_data_router", return_value=fake_router):
        exit_code = main(["--ticker", "600519"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "600519" in captured.out
    assert "贵州茅台" in captured.out


def test_cli_smoke_unknown_ticker_returns_1(capsys):
    """Unknown ticker should result in empty df and exit code 1."""
    fake_router = AsyncMock()
    fake_router.get_realtime_quote.return_value = pd.DataFrame()
    fake_router.get_daily_history.return_value = pd.DataFrame()

    with patch("valor.cli.main.get_data_router", return_value=fake_router):
        exit_code = main(["--ticker", "999999"])

    assert exit_code == 1


def test_cli_smoke_falls_back_to_daily_history_when_realtime_empty(capsys):
    """When realtime quote is empty, CLI should fall back to daily history."""
    fake_router = AsyncMock()
    fake_router.get_realtime_quote.return_value = pd.DataFrame()
    fake_router.get_daily_history.return_value = pd.DataFrame(
        {
            "date": ["2026-07-15"],
            "code": ["sh.600519"],
            "open": ["1203.66"],
            "close": ["1251.06"],
        }
    )

    with patch("valor.cli.main.get_data_router", return_value=fake_router):
        exit_code = main(["--ticker", "600519"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "600519" in captured.out
    assert "1251.06" in captured.out

