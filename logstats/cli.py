"""命令行入口。

用法：
    python -m logstats.cli --file sample/app.log \
        --from 2026-09-22T00:00 --to 2026-09-22T02:00 \
        --window-minutes 60 --top 5
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from typing import Sequence

from .parser import Record, parse_lines
from .stats import by_component, filter_range, window_counts


def parse_bound(text: str) -> datetime:
    """把 --from / --to 解析成 UTC 时间轴上的时刻。"""
    cleaned = text.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    moment = datetime.fromisoformat(cleaned)
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc).replace(tzinfo=None)
    return moment.replace(tzinfo=None)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="logstats", description="日志延迟统计")
    parser.add_argument("--file", required=True, help="日志文件路径")
    parser.add_argument("--from", dest="start", required=True, help="统计起始时间（UTC，含）")
    parser.add_argument("--to", dest="end", required=True, help="统计结束时间（UTC，不含）")
    parser.add_argument("--window-minutes", type=int, default=60, help="窗口长度（分钟）")
    parser.add_argument("--top", type=int, default=5, help="按组件汇总时最多打印几行")
    return parser


def render(records: Sequence[Record], start: datetime, end: datetime, window: int, top: int) -> str:
    """生成要打印的报告文本。"""
    lines: list[str] = []
    windows = window_counts(records, start, end, window)
    lines.append(f"窗口统计（窗口 {window} 分钟）")
    for moment, count in windows:
        lines.append(f"{moment.isoformat(timespec='minutes')}  {count}")
    total = sum(count for _, count in windows)
    in_range = len(filter_range(records, start, end))
    lines.append(f"合计 {total} 条 / 区间内 {in_range} 条 / 文件 {len(records)} 条")
    lines.append("")
    lines.append("组件 P95（毫秒）")
    lines.append(f"{'组件':<8}{'条数':>6}{'P95':>8}")
    for name, count, p95 in by_component(in_range_records(records, start, end))[:top]:
        lines.append(f"{name:<8}{count:>6}{p95:>8}")
    return "\n".join(lines)


def in_range_records(records: Sequence[Record], start: datetime, end: datetime) -> list[Record]:
    return filter_range(records, start, end)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    start, end = parse_bound(args.start), parse_bound(args.end)
    with open(args.file, encoding="utf-8") as handle:
        records, errors = parse_lines(handle)
    print(render(records, start, end, args.window_minutes, args.top))
    if errors:
        print("")
        print(f"解析失败 {len(errors)} 行")
        for number, reason in errors[:5]:
            print(f"  第 {number} 行：{reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
