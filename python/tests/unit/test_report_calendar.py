"""Unit tests for report_calendar pure functions."""

from datetime import date

from valor.adapters.data.report_calendar import (
    deadline_for,
    next_expected_report_date,
    should_refresh_reports,
)


def test_deadline_for_q1() -> None:
    assert deadline_for(2026, 1) == date(2026, 4, 30)


def test_deadline_for_q2() -> None:
    assert deadline_for(2026, 2) == date(2026, 8, 31)


def test_deadline_for_q3() -> None:
    assert deadline_for(2026, 3) == date(2026, 10, 31)


def test_deadline_for_q4_falls_next_year() -> None:
    """Q4 (年报) 截止日落在次年 4/30。"""
    assert deadline_for(2026, 4) == date(2027, 4, 30)


def test_next_expected_after_annual_before_q1_deadline() -> None:
    """缓存最新是 2025 年报(12/31)，今天在 Q1 截止日前 -> 无需刷新。"""
    latest = date(2025, 12, 31)
    today = date(2026, 4, 1)
    assert next_expected_report_date(latest, today) is None


def test_next_expected_after_annual_after_q1_deadline() -> None:
    """缓存最新是 2025 年报，今天已过 Q1 截止日 -> 应刷新。"""
    latest = date(2025, 12, 31)
    today = date(2026, 7, 19)
    assert next_expected_report_date(latest, today) == date(2026, 4, 30)


def test_next_expected_after_q1_before_q2_deadline() -> None:
    """缓存最新是 2026 Q1(3/31)，今天在 Q2 截止日前 -> 无需刷新。"""
    latest = date(2026, 3, 31)
    today = date(2026, 8, 1)
    assert next_expected_report_date(latest, today) is None


def test_next_expected_after_q1_after_q2_deadline() -> None:
    """缓存最新是 2026 Q1，今天已过 Q2 截止日 -> 应刷新。"""
    latest = date(2026, 3, 31)
    today = date(2026, 9, 15)
    assert next_expected_report_date(latest, today) == date(2026, 8, 31)


def test_next_expected_after_q3_before_q4_deadline() -> None:
    """缓存最新是 2026 Q3(9/30)，今天在年报截止日前 -> 无需刷新。"""
    latest = date(2026, 9, 30)
    today = date(2026, 12, 31)
    assert next_expected_report_date(latest, today) is None


def test_next_expected_after_q3_after_q4_deadline() -> None:
    """缓存最新是 2025 Q3，今天已过 2025 年报截止日(2026/4/30) -> 应刷新。"""
    latest = date(2025, 9, 30)
    today = date(2026, 5, 15)
    assert next_expected_report_date(latest, today) == date(2026, 4, 30)


def test_should_refresh_when_cache_empty() -> None:
    """缓存为空 -> 必须刷新。"""
    assert should_refresh_reports(None) is True


def test_should_refresh_when_new_period_due() -> None:
    """缓存有数据但新季度应已披露 -> 刷新。"""
    latest = date(2025, 12, 31)
    today = date(2026, 7, 19)
    assert should_refresh_reports(latest, today) is True


def test_should_not_refresh_when_latest_covers_current_period() -> None:
    """缓存最新是 2026 中报(6/30)，今天 7/19，Q3 截止 10/31 还没到 -> 不刷新。"""
    latest = date(2026, 6, 30)
    today = date(2026, 7, 19)
    assert should_refresh_reports(latest, today) is False