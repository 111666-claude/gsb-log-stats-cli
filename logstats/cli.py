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

from .parser import ParseError, parse_line
from .stats import Analyzer


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
    parser.add_argument(
        "--grace-minutes",
        type=int,
        default=None,
        help="乱序容忍的迟到时长（分钟），默认等于窗口长度；超限计入「迟到丢弃」",
    )
    parser.add_argument("--exact", action="store_true", help="保留全部样本精确计算 P95（用于对照，内存随记录数增长）")
    return parser


def render(analyzer: Analyzer, window: int, top: int) -> str:
    """生成要打印的报告文本。"""
    lines: list[str] = []
    lines.append(f"窗口统计（窗口 {window} 分钟）")
    for moment, count in analyzer.window_rows():
        lines.append(f"{moment.isoformat(timespec='minutes')}  {count}")
    lines.append(f"合计 {analyzer.total} 条 / 区间内 {analyzer.in_range} 条 / 文件 {analyzer.file_total} 条")
    lines.append(f"迟到丢弃 {analyzer.late_dropped} 条")
    lines.append(f"误差上界 ±{analyzer.error_bound():g} ms")
    lines.append("")
    lines.append("组件 P95（毫秒）")
    lines.append(f"{'组件':<8}{'条数':>6}{'P95':>8}")
    for name, count, p95 in analyzer.component_rows()[:top]:
        lines.append(f"{name:<8}{count:>6}{p95:>8g}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    start, end = parse_bound(args.start), parse_bound(args.end)
    grace = args.window_minutes if args.grace_minutes is None else args.grace_minutes
    try:
        analyzer = Analyzer(start, end, args.window_minutes, grace_minutes=grace, exact=args.exact)
    except ValueError as exc:
        raise SystemExit(f"参数错误：{exc}")
    errors: list[tuple[int, str]] = []
    with open(args.file, encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                analyzer.add(parse_line(line))
            except ParseError as exc:
                errors.append((number, str(exc)))
    print(render(analyzer, args.window_minutes, args.top))
    if errors:
        print("")
        print(f"解析失败 {len(errors)} 行")
        for number, reason in errors[:5]:
            print(f"  第 {number} 行：{reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
