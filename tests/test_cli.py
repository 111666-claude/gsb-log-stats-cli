import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from logstats.cli import main, parse_bound, render
from logstats.parser import parse_line
from logstats.stats import Analyzer


def build_analyzer(lines, start, end, window, **kwargs):
    analyzer = Analyzer(parse_bound(start), parse_bound(end), window, **kwargs)
    for line in lines:
        analyzer.add(parse_line(line))
    return analyzer


class ParseBoundTest(unittest.TestCase):
    def test_utc_offset_is_normalised(self):
        self.assertEqual(parse_bound("2026-09-22T00:00"), parse_bound("2026-09-22T08:00+08:00"))


class RenderTest(unittest.TestCase):
    def test_reports_window_rows_and_component_table(self):
        analyzer = build_analyzer(
            [
                "2026-09-22T00:10:00 INFO [api] handled in 30ms",
                "2026-09-22T00:40:00 INFO [api] handled in 40ms",
                "2026-09-22T00:50:00 INFO [db] handled in 20ms",
            ],
            "2026-09-22T00:00",
            "2026-09-22T01:00",
            30,
        )
        text = render(analyzer, 30, 5)
        self.assertIn("合计 3 条", text)
        self.assertIn("迟到丢弃 0 条", text)
        self.assertIn("误差上界 ±", text)
        self.assertIn("api", text)
        self.assertIn("db", text)


class MainTest(unittest.TestCase):
    def run_main(self, content, *extra):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "app.log")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(content)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main(["--file", path, "--from", "2026-09-22T00:00", "--to", "2026-09-22T02:00", *extra])
        return code, buffer.getvalue()

    def test_runs_on_file(self):
        code, output = self.run_main("2026-09-22T00:10:00 INFO [api] handled in 30ms\n")
        self.assertEqual(0, code)
        self.assertIn("窗口统计", output)
        self.assertIn("迟到丢弃 0 条", output)
        self.assertIn("误差上界 ±0.5 ms", output)

    def test_exact_mode_reports_zero_error_bound(self):
        code, output = self.run_main("2026-09-22T00:10:00 INFO [api] handled in 30ms\n", "--exact")
        self.assertEqual(0, code)
        self.assertIn("误差上界 ±0 ms", output)

    def test_offset_timestamps_fall_into_utc_windows(self):
        content = (
            "2026-09-22T00:10:00 INFO [api] handled in 30ms\n"
            "2026-09-22T09:20:00+08:00 INFO [db] handled in 10ms\n"
            "2026-09-22T01:30:00Z INFO [db] handled in 20ms\n"
        )
        code, output = self.run_main(content, "--exact")
        self.assertEqual(0, code)
        self.assertIn("合计 3 条 / 区间内 3 条 / 文件 3 条", output)
        self.assertIn("2026-09-22T01:00  2", output)

    def test_sample_log_matches_readme_figures(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main([
                "--file", "sample/app.log",
                "--from", "2026-09-22T00:00",
                "--to", "2026-09-22T02:00",
                "--exact",
            ])
        self.assertEqual(0, code)
        output = buffer.getvalue()
        self.assertIn("2026-09-22T00:00  10", output)
        self.assertIn("2026-09-22T01:00  16", output)
        self.assertIn("合计 26 条 / 区间内 26 条 / 文件 26 条", output)
        self.assertIn("迟到丢弃 0 条", output)
        self.assertIn(f"{'api':<8}{20:>6}{190:>8}", output)
        self.assertIn(f"{'db':<8}{6:>6}{25:>8}", output)


if __name__ == "__main__":
    unittest.main()
