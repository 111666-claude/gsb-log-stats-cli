"""聚合统计：窗口计数、百分位、直方图估算、流式分析器。"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Sequence

from .parser import Record

# 直方图桶数上限，内存占用与记录数无关
MAX_BUCKETS = 4096


def filter_range(records: Sequence[Record], start: datetime, end: datetime) -> list[Record]:
    """保留 [start, end) 半开区间内的记录（口径见 README）。"""
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
    """p 百分位（最近秩）；样本为空返回 None。"""
    if not values:
        return None
    if not 0 < p <= 100:
        raise ValueError("p 必须落在 (0, 100] 区间内")
    ordered = sorted(values)
    rank = math.ceil(len(ordered) * p / 100)
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
    """固定桶数上限的等宽直方图，用于在常量内存内估算百分位。

    桶宽从 1 开始；当值域跨度超过 max_buckets 个桶时，桶宽翻倍、
    相邻桶两两合并，因此桶数永远不超过 max_buckets。百分位估计取
    目标桶的中点，与真实最近秩百分位的偏差不超过半个桶宽
    （error_bound 属性）。
    """

    def __init__(self, max_buckets: int = MAX_BUCKETS) -> None:
        if max_buckets < 1:
            raise ValueError("max_buckets 必须是正整数")
        self.max_buckets = max_buckets
        self.width = 1
        self.buckets: dict[int, int] = {}
        self.count = 0
        self._min_index: int | None = None
        self._max_index: int | None = None

    def add(self, value: int) -> None:
        if value < 0:
            raise ValueError("直方图只支持非负值")
        index = value // self.width
        self.buckets[index] = self.buckets.get(index, 0) + 1
        self.count += 1
        self._min_index = index if self._min_index is None else min(self._min_index, index)
        self._max_index = index if self._max_index is None else max(self._max_index, index)
        while self._max_index - self._min_index + 1 > self.max_buckets:
            self._merge()

    def _merge(self) -> None:
        """桶宽翻倍，相邻桶两两合并。"""
        self.width *= 2
        merged: dict[int, int] = {}
        for index, count in self.buckets.items():
            new_index = index // 2
            merged[new_index] = merged.get(new_index, 0) + count
        self.buckets = merged
        self._min_index //= 2
        self._max_index //= 2

    @property
    def error_bound(self) -> float:
        """估计值与真实最近秩百分位的最大偏差：半个桶宽。"""
        return self.width / 2

    def percentile(self, p: float) -> float | None:
        """估算 p 百分位，取目标桶中点；样本为空返回 None。"""
        if self.count == 0:
            return None
        if not 0 < p <= 100:
            raise ValueError("p 必须落在 (0, 100] 区间内")
        rank = math.ceil(self.count * p / 100)
        cumulative = 0
        for index in sorted(self.buckets):
            cumulative += self.buckets[index]
            if cumulative >= rank:
                return index * self.width + self.width / 2
        raise AssertionError("累计计数与样本总数不一致")


class Analyzer:
    """流式分析器：逐条喂入记录，不保留全部样本。

    - 记录可以按任意顺序到达，按事件时间（UTC）归窗；
    - 水位线 = 已见记录的最大事件时间；事件时间早于 水位线 - grace
    的记录视为迟到超限，计入 late_dropped，不进任何窗口；
    - grace 默认等于窗口长度；
    - exact=False 时组件延迟用 Histogram 估算，内存与记录数无关；
      exact=True 时保留全部延迟样本做精确对照。
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
        if end <= start:
            raise ValueError("end 必须晚于 start")
        if grace_minutes is not None and grace_minutes < 0:
            raise ValueError("grace_minutes 不能为负")
        self.start = start
        self.end = end
        self.step = timedelta(minutes=window_minutes)
        self.grace = timedelta(minutes=window_minutes if grace_minutes is None else grace_minutes)
        self.exact = exact
        self.max_buckets = max_buckets
        num_windows = math.ceil((end - start) / self.step)
        self.windows: list[int] = [0] * num_windows
        self.file_total = 0
        self.in_range = 0
        self.late_dropped = 0
        self._watermark: datetime | None = None
        self._components: dict[str, Histogram | list[int]] = {}

    def add(self, record: Record) -> None:
        self.file_total += 1
        moment = record.timestamp
        if self._watermark is None or moment > self._watermark:
            self._watermark = moment
        if not (self.start <= moment < self.end):
            return
        self.in_range += 1
        if moment < self._watermark - self.grace:
            self.late_dropped += 1
            return
        index = (moment - self.start) // self.step
        self.windows[index] += 1
        store = self._components.get(record.component)
        if self.exact:
            if store is None:
                store = self._components[record.component] = []
            store.append(record.latency_ms)
        else:
            if store is None:
                store = self._components[record.component] = Histogram(self.max_buckets)
            store.add(record.latency_ms)

    def window_rows(self) -> list[tuple[datetime, int]]:
        """[(窗口起点, 条数), ...]，窗口为半开区间。"""
        return [(self.start + i * self.step, count) for i, count in enumerate(self.windows)]

    @property
    def total(self) -> int:
        """落进窗口的总条数；total + late_dropped == in_range。"""
        return sum(self.windows)

    def error_bound(self) -> float:
        """所有组件 P95 估算误差上界（半个桶宽的最大值）；精确模式为 0。"""
        if self.exact:
            return 0
        bounds = [store.error_bound for store in self._components.values() if store.count]
        return max(bounds, default=0)

    def component_rows(self) -> list[tuple[str, int, float | None]]:
        """[(组件, 条数, P95)]，按 P95 降序、组件名升序。"""
        rows = []
        for name, store in self._components.items():
            if self.exact:
                rows.append((name, len(store), percentile(store, 95)))
            else:
                rows.append((name, store.count, store.percentile(95)))
        rows.sort(key=lambda row: (-(row[2] or 0), row[0]))
        return rows
