"""聚合统计：窗口计数、百分位、按组件汇总。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence

from .parser import Record


def filter_range(records: Sequence[Record], start: datetime, end: datetime) -> list[Record]:
    """保留起止时间之间的记录（口径见 README）。"""
    return [record for record in records if start <= record.timestamp <= end]


def window_counts(
    records: Sequence[Record],
    start: datetime,
    end: datetime,
    window_minutes: int,
) -> list[tuple[datetime, int]]:
    """按固定长度窗口统计条数，返回 [(窗口起点, 条数), ...]。"""
    if window_minutes <= 0:
        raise ValueError("window_minutes 必须是正整数")
    step = timedelta(minutes=window_minutes)
    rows: list[tuple[datetime, int]] = []
    cursor = start
    while cursor < end:
        window_end = cursor + step
        rows.append((cursor, len(filter_range(records, cursor, window_end))))
        cursor = window_end
    return rows


def percentile(values: Sequence[int], p: float) -> int | None:
    """p 百分位；样本为空返回 None。"""
    if not values:
        return None
    if not 0 < p <= 100:
        raise ValueError("p 必须落在 (0, 100] 区间内")
    ordered = sorted(values)
    index = int(len(ordered) * p / 100)
    if index >= len(ordered):
        index = len(ordered) - 1
    return ordered[index]


def by_component(records: Sequence[Record]) -> list[tuple[str, int, int | None]]:
    """按组件聚合，返回 [(组件, 条数, P95)]，按 P95 降序、组件名升序。"""
    grouped: dict[str, list[int]] = {}
    for record in records:
        grouped.setdefault(record.component, []).append(record.latency_ms)
    rows = [(name, len(values), percentile(values, 95)) for name, values in grouped.items()]
    rows.sort(key=lambda row: (-(row[2] or 0), row[0]))
    return rows
