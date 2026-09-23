import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from logstats.cli import main, parse_bound, render
from logstats.parser import parse_lines


class ParseBoundTest(unittest.TestCase):
    def test_utc_offset_is_normalised(self):
        self.assertEqual(parse_bound("2026-09-22T00:00"), parse_bound("2026-09-22T08:00+08:00"))


class RenderTest(unittest.TestCase):
    def test_reports_window_rows_and_component_table(self):
        records, errors = parse_lines(
            [
                "2026-09-22T00:10:00 INFO [api] handled in 30ms",
                "2026-09-22T00:40:00 INFO [api] handled in 40ms",
                "2026-09-22T00:50:00 INFO [db] handled in 20ms",
            ]
        )
        self.assertEqual([], errors)
        text = render(records, parse_bound("2026-09-22T00:00"), parse_bound("2026-09-22T01:00"), 30, 5)
        self.assertIn("合计 3 条", text)
        self.assertIn("api", text)
        self.assertIn("db", text)


class MainTest(unittest.TestCase):
    def test_runs_on_file(self):
        content = "2026-09-22T00:10:00 INFO [api] handled in 30ms\n"
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "app.log")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(content)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main(["--file", path, "--from", "2026-09-22T00:00", "--to", "2026-09-22T01:00"])
        self.assertEqual(0, code)
        self.assertIn("窗口统计", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
