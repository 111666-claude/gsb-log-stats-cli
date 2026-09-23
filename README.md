# logstats

一个小型日志延迟统计命令行工具，只用 Python 标准库。

```
python -m logstats.cli --file sample/app.log \
    --from 2026-09-22T00:00 --to 2026-09-22T02:00 \
    --window-minutes 60 --top 5
python -m unittest discover -s tests -v
```

## 日志格式

每行一条：

```
<ISO 时间戳> <LEVEL> [组件] handled in <毫秒>ms
```

例如：

```
2026-09-22T00:05:00 INFO [api] handled in 10ms
2026-09-22T09:10:00+08:00 INFO [db] handled in 5ms
```

空行忽略；格式不对的行不会中断统计，而是计入「解析失败」并在结尾列出。

## 统计口径

- **时间轴统一按 UTC**：日志行里带偏移的时间戳（`+08:00`、`Z`）先换算到 UTC，
  再和 `--from` / `--to` 比较；`--from` / `--to` 不带偏移时按 UTC 解释。
- **窗口是半开区间**：窗口 `[起点, 起点+窗口长度)`，一条记录只会落进一个窗口，
  相邻窗口的条数相加等于区间内的总条数。
- **百分位用最近秩（nearest-rank）**：对 `n` 个样本求 `p` 百分位，取排序后
  第 `ceil(n * p / 100)` 个（1 起数）；样本为空返回 `None`。

`--from` 含、`--to` 不含。

## 输出

```
窗口统计（窗口 60 分钟）
2026-09-22T00:00  10
2026-09-22T01:00  16
合计 26 条 / 区间内 26 条 / 文件 26 条

组件 P95（毫秒）
组件      条数   P95
api       20     190
db        6      25
```

## 目录

```
logstats/
  parser.py   日志行解析
  stats.py    窗口计数、百分位、按组件汇总
  cli.py      命令行入口
tests/        unittest 用例
sample/app.log  示例日志
```
