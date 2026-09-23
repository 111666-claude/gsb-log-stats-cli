"""日志行解析。

格式见 README：
    <ISO 时间戳> <LEVEL> [组件] handled in <毫秒>ms
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

LINE_RE = re.compile(
    r"^(?P<ts>\S+)\s+(?P<level>[A-Z]+)\s+\[(?P<component>[^\]]+)\]\s+handled in (?P<latency>\d+)ms$"
)


class ParseError(ValueError):
    """日志行不符合格式时抛出。"""


@dataclass(frozen=True)
class Record:
    """一条日志记录。timestamp 是用于分窗的时间轴时刻。"""

    timestamp: datetime
    level: str
    component: str
    latency_ms: int


def parse_timestamp(text: str) -> datetime:
    """把时间戳文本解析成 UTC 时间轴上的时刻（naive，口径见 README）。"""
    cleaned = text.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(cleaned)
    except ValueError as exc:
        raise ParseError(f"无法解析时间戳：{text!r}") from exc
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc)
    return moment.replace(tzinfo=None)


def parse_line(line: str) -> Record:
    """解析一行日志，格式不对抛 ParseError。"""
    matched = LINE_RE.match(line.strip())
    if not matched:
        raise ParseError(f"日志行格式不符：{line.strip()!r}")
    return Record(
        timestamp=parse_timestamp(matched.group("ts")),
        level=matched.group("level"),
        component=matched.group("component"),
        latency_ms=int(matched.group("latency")),
    )


def parse_lines(lines: Iterable[str]) -> tuple[list[Record], list[tuple[int, str]]]:
    """返回 (记录列表, 错误列表)，错误元素是 (行号, 原因)。空行直接跳过。"""
    records: list[Record] = []
    errors: list[tuple[int, str]] = []
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            records.append(parse_line(line))
        except ParseError as exc:
            errors.append((number, str(exc)))
    return records, errors
