"""聚合统计：窗口计数、百分位、直方图估算、流式分析器。

口径见 README：
- 时间轴统一按 UTC（解析时已换算）；
- 窗口是半开区间 [起点, 起点+窗口长度)；
- 百分位用最近秩（nearest-rank），样本为空返回 None；
- 流式分析器按事件时间归窗，水位线以外的迟到记录计入「迟到丢弃」。
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Sequence

from .parser import Record

MAX_BUCKETS = 4096


def filter_range(records: Sequence[Record], start: datetime, end: datetime) -> list[Record]:
    """保留 [start, end) 内的记录（半开区间，口径见 README）。"""
    return [record for record in records if start <= record.timestamp < end]


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
    rank = math.ceil(len(ordered) * p / 100)  # 最近秩，1 起数
    return ordered[rank - 1]


def by_component(records: Sequence[Record]) -> list[tuple[str, int, int | None]]:
    """按组件聚合，返回 [(组件, 条数, P95)]，按 P95 降序、组件名升序。"""
    grouped: dict[str, list[int]] = {}
    for record in records:
        grouped.setdefault(record.component, []).append(record.latency_ms)
    rows = [(name, len(values), percentile(values, 95)) for name, values in grouped.items()]
    rows.sort(key=lambda row: (-(row[2] or 0), row[0]))
    return rows


class Histogram:
    """固定桶数上限的直方图，用于估算百分位。

    桶宽始终是 2 的幂：当新值超出当前覆盖范围时，桶宽翻倍并合并相邻桶，
    保证桶的总数不超过 max_buckets。估算值取所在桶的中点，
    与真实最近秩取值之差的上界为半个桶宽。
    """

    def __init__(self, max_buckets: int = MAX_BUCKETS) -> None:
        if max_buckets < 1:
            raise ValueError("max_buckets 必须是正整数")
        self.max_buckets = max_buckets
        self.width = 1
        self.buckets: dict[int, int] = {}
        self.count = 0

    def add(self, value: int) -> None:
        if value < 0:
            raise ValueError("只支持非负延迟")
        while value >= self.width * self.max_buckets:
            self._double_width()
        index = value // self.width
        self.buckets[index] = self.buckets.get(index, 0) + 1
        self.count += 1

    def _double_width(self) -> None:
        self.width *= 2
        merged: dict[int, int] = {}
        for index, amount in self.buckets.items():
            new_index = index // 2
            merged[new_index] = merged.get(new_index, 0) + amount
        self.buckets = merged

    @property
    def error_bound(self) -> float:
        """估算值与真实最近秩取值之差的上界（半个桶宽）。"""
        return self.width / 2

    def percentile(self, p: float) -> float | None:
        """估算 p 百分位；样本为空返回 None。"""
        if self.count == 0:
            return None
        if not 0 < p <= 100:
            raise ValueError("p 必须落在 (0, 100] 区间内")
        rank = math.ceil(self.count * p / 100)  # 最近秩，1 起数
        cumulative = 0
        for index in sorted(self.buckets):
            cumulative += self.buckets[index]
            if cumulative >= rank:
                return index * self.width + self.width / 2
        raise AssertionError("直方图计数与秩不匹配")


class Analyzer:
    """流式分析器：逐条喂入记录，不保留全部样本。

    - 记录可按任意顺序到达，按事件时间归窗；
    - 水位线 = 已见最大事件时间 - grace，早于水位线的记录计入「迟到丢弃」，
      不会悄悄算进别的窗口；
    - exact=False 时按组件维护直方图估算 P95/P99，
      exact=True 时保留样本精确计算（对照模式）。
    """

    def __init__(
        self,
        start: datetime,
        end: datetime,
        window_minutes: int,
        grace_minutes: int | None = None,
        exact: bool = False,
        max_buckets: int = MAX_BUCKETS,
    ) -> None:
        if window_minutes <= 0:
            raise ValueError("window_minutes 必须是正整数")
        self.start = start
        self.end = end
        self.window_minutes = window_minutes
        self.step = timedelta(minutes=window_minutes)
        self.grace = (
            timedelta(minutes=grace_minutes)
            if grace_minutes is not None
            else self.step
        )
        self.exact = exact
        self.max_buckets = max_buckets
        span = end - start
        self.num_windows = 0 if span <= timedelta(0) else -(-span // self.step)
        self.windows: dict[int, int] = {}
        self.components: dict[str, Histogram | list[int]] = {}
        self.total = 0
        self.in_range = 0
        self.late_dropped = 0
        self.max_seen: datetime | None = None

    def add(self, record: Record) -> None:
        self.total += 1
        timestamp = record.timestamp
        if not (self.start <= timestamp < self.end):
            self._advance_watermark(timestamp)
            return
        if self.max_seen is not None and timestamp < self.max_seen - self.grace:
            self.late_dropped += 1
            return
        self._advance_watermark(timestamp)
        self.in_range += 1
        window_index = (timestamp - self.start) // self.step
        self.windows[window_index] = self.windows.get(window_index, 0) + 1
        if self.exact:
            self.components.setdefault(record.component, []).append(record.latency_ms)
        else:
            histogram = self.components.setdefault(
                record.component, Histogram(self.max_buckets)
            )
            histogram.add(record.latency_ms)

    def _advance_watermark(self, timestamp: datetime) -> None:
        if self.max_seen is None or timestamp > self.max_seen:
            self.max_seen = timestamp

    def window_rows(self) -> list[tuple[datetime, int]]:
        """按窗口起点升序返回 [(窗口起点, 条数), ...]，空窗口也会列出。"""
        return [
            (self.start + index * self.step, self.windows.get(index, 0))
            for index in range(self.num_windows)
        ]

    def component_rows(
        self, p: float = 95
    ) -> list[tuple[str, int, float | int | None, float]]:
        """返回 [(组件, 条数, P95 估算, 误差上界)]，按 P95 降序、组件名升序。"""
        rows: list[tuple[str, int, float | int | None, float]] = []
        for name, store in self.components.items():
            if self.exact:
                value: float | int | None = percentile(store, p)
                bound = 0.0
                count = len(store)
            else:
                value = store.percentile(p)
                bound = store.error_bound
                count = store.count
            rows.append((name, count, value, bound))
        rows.sort(key=lambda row: (-(row[2] or 0), row[0]))
        return rows

    @property
    def error_bound(self) -> float:
        """当前所有组件中最大的估算误差上界（毫秒）。"""
        if self.exact or not self.components:
            return 0.0
        return max(store.error_bound for store in self.components.values())
