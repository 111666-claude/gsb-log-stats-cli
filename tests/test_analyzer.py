import random
import unittest
from datetime import datetime, timedelta

from logstats.parser import Record
from logstats.stats import Analyzer

START = datetime(2026, 9, 22, 0, 0)
END = datetime(2026, 9, 22, 4, 0)


def make(hour=0, minute=0, component="api", latency=10):
    return Record(
        timestamp=datetime(2026, 9, 22, hour, minute, 0),
        level="INFO",
        component=component,
        latency_ms=latency,
    )


class WindowAssignmentTest(unittest.TestCase):
    def test_out_of_order_records_land_in_correct_windows(self):
        analyzer = Analyzer(START, END, 60, grace_minutes=240)
        records = [make(2, 30), make(0, 10), make(1, 5), make(0, 45), make(2, 1)]
        for record in records:
            analyzer.add(record)
        counts = [count for _, count in analyzer.window_rows()]
        self.assertEqual([2, 1, 2, 0], counts)
        self.assertEqual(5, analyzer.total)
        self.assertEqual(5, analyzer.in_range)
        self.assertEqual(0, analyzer.late_dropped)

    def test_boundary_record_counted_once(self):
        analyzer = Analyzer(START, END, 60)
        for record in [make(0, 0), make(1, 0), make(1, 59)]:
            analyzer.add(record)
        counts = [count for _, count in analyzer.window_rows()]
        self.assertEqual([1, 2, 0, 0], counts)
        self.assertEqual(analyzer.total, analyzer.in_range)

    def test_end_is_exclusive(self):
        analyzer = Analyzer(START, END, 60)
        analyzer.add(make(4, 0))
        self.assertEqual(0, analyzer.in_range)
        self.assertEqual(0, analyzer.total)
        self.assertEqual(1, analyzer.file_total)


class GraceTest(unittest.TestCase):
    def test_default_grace_equals_window(self):
        analyzer = Analyzer(START, END, 60)
        self.assertEqual(timedelta(minutes=60), analyzer.grace)

    def test_late_within_grace_is_accepted(self):
        analyzer = Analyzer(START, END, 60, grace_minutes=30)
        analyzer.add(make(2, 0))
        analyzer.add(make(1, 45))
        self.assertEqual(0, analyzer.late_dropped)
        self.assertEqual([0, 1, 1, 0], [count for _, count in analyzer.window_rows()])

    def test_late_beyond_grace_is_dropped_not_rewindowed(self):
        analyzer = Analyzer(START, END, 60, grace_minutes=30)
        analyzer.add(make(2, 0))
        analyzer.add(make(1, 0))
        self.assertEqual(1, analyzer.late_dropped)
        self.assertEqual([0, 0, 1, 0], [count for _, count in analyzer.window_rows()])
        self.assertEqual(analyzer.total + analyzer.late_dropped, analyzer.in_range)

    def test_out_of_range_records_are_not_late_drops(self):
        analyzer = Analyzer(START, END, 60, grace_minutes=30)
        analyzer.add(make(3, 0))
        analyzer.add(Record(datetime(2020, 1, 1), "INFO", "api", 5))
        self.assertEqual(0, analyzer.late_dropped)
        self.assertEqual(2, analyzer.file_total)
        self.assertEqual(1, analyzer.in_range)

    def test_rejects_negative_grace(self):
        with self.assertRaises(ValueError):
            Analyzer(START, END, 60, grace_minutes=-1)


class ExactVsEstimateTest(unittest.TestCase):
    def make_stream(self):
        rng = random.Random(7)
        records = []
        for _ in range(3000):
            minute = rng.randrange(0, 240)
            component = rng.choice(["api", "db", "queue"])
            latency = rng.randrange(0, 50000)
            records.append(make(minute // 60, minute % 60, component, latency))
        return records

    def test_estimate_matches_exact_within_declared_bound(self):
        records = self.make_stream()
        estimate = Analyzer(START, END, 60)
        exact = Analyzer(START, END, 60, exact=True)
        for record in records:
            estimate.add(record)
            exact.add(record)
        self.assertEqual(exact.total, estimate.total)
        self.assertEqual(exact.late_dropped, estimate.late_dropped)
        exact_rows = {name: (count, p95) for name, count, p95 in exact.component_rows()}
        bound = estimate.error_bound()
        self.assertGreater(bound, 0)
        for name, count, p95 in estimate.component_rows():
            exact_count, exact_p95 = exact_rows[name]
            self.assertEqual(exact_count, count)
            self.assertAlmostEqual(exact_p95, p95, delta=bound)

    def test_exact_mode_reports_zero_bound(self):
        analyzer = Analyzer(START, END, 60, exact=True)
        analyzer.add(make(0, 5))
        self.assertEqual(0, analyzer.error_bound())


if __name__ == "__main__":
    unittest.main()
