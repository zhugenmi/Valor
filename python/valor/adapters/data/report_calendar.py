"""A 股财报披露日历 - 纯函数，无 I/O 依赖。

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from __future__ import annotations

from datetime import date
from typing import Literal

# A 股季度报告法定披露截止日（月, 日）
# Q1 报: 4/30；中报(Q2): 8/31；三季报(Q3): 10/31；年报(Q4): 次年 4/30
DISCLOSURE_DEADLINES: dict[int, tuple[int, int]] = {
    1: (4, 30),
    2: (8, 31),
    3: (10, 31),
    4: (4, 30),
}

ReportQuarter = Literal[1, 2, 3, 4]


def deadline_for(year: int, quarter: ReportQuarter) -> date:
    """返回指定年度指定季度的披露截止日。Q4 截止日落在次年。"""
    month, day = DISCLOSURE_DEADLINES[quarter]
    return date(year + 1, month, day) if quarter == 4 else date(year, month, day)


def next_expected_report_date(
    latest_report_date: date, today: date | None = None
) -> date | None:
    """根据缓存里最新的报告日，推算下一个"应该已披露"的报告截止日。

    若今天已经过了下一季度的披露截止日，但缓存仍停留在 latest_report_date，
    说明有新季度报告应该已经披露 -> 触发刷新。

    返回 None 表示缓存里的报告日已经覆盖到当前最新季度，无需刷新。
    """
    today = today or date.today()
    y, m = latest_report_date.year, latest_report_date.month

    # 推算 latest_report_date 对应的季度（基于季末日期）
    if m <= 3:
        current_q, current_year = 1, y        # Q1 (end 3/31)
    elif m <= 6:
        current_q, current_year = 2, y        # Q2 (end 6/30)
    elif m <= 9:
        current_q, current_year = 3, y        # Q3 (end 9/30)
    else:
        current_q, current_year = 4, y        # Q4 (end 12/31)

    # 下一个应该已披露的季度
    if current_q == 4:
        next_q, next_year = 1, current_year + 1
    else:
        next_q, next_year = current_q + 1, current_year

    next_deadline = deadline_for(next_year, next_q)
    return next_deadline if today >= next_deadline else None


def should_refresh_reports(
    latest_report_date: date | None, today: date | None = None
) -> bool:
    """判断三大报表是否需要刷新。

    - 缓存为空 -> True（首次拉取）
    - next_expected_report_date 返回非 None -> True（有新季度应已披露）
    - 否则 False
    """
    if latest_report_date is None:
        return True
    return next_expected_report_date(latest_report_date, today) is not None