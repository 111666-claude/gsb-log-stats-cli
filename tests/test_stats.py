import unittest
from datetime import datetime

from logstats.parser import Record
from logstats.stats import by_component, filter_range, percentile, window_counts


def make(minute: int, component: str = "api", latency: int = 10) -> Record:
    return Record(
        timestamp=datetime(2026, 9, 22, 0, minute, 0),
        level="INFO",
        component=component,
        latency_ms=latency,
    )


class FilterRangeTest(unittest.TestCase):
    def test_keeps_records_inside(self):
        records = [make(5), make(10), make(15)]
        kept = filter_range(records, datetime(2026, 9, 22, 0, 8), datetime(2026, 9, 22, 0, 12))
        self.assertEqual([10], [record.timestamp.minute for record in kept])

    def test_half_open_interval(self):
        records = [make(8), make(12)]
        kept = filter_range(records, datetime(2026, 9, 22, 0, 8), datetime(2026, 9, 22, 0, 12))
        self.assertEqual([8], [record.timestamp.minute for record in kept])


class WindowCountsTest(unittest.TestCase):
    def test_two_windows_without_boundary_records(self):
        records = [make(5), make(15), make(25), make(35), make(45), make(55)]
        rows = window_counts(records, datetime(2026, 9, 22, 0, 0), datetime(2026, 9, 22, 1, 0), 30)
        self.assertEqual([3, 3], [count for _, count in rows])

    def test_boundary_record_counted_once(self):
        records = [make(0), make(30), make(59)]
        rows = window_counts(records, datetime(2026, 9, 22, 0, 0), datetime(2026, 9, 22, 1, 0), 30)
        self.assertEqual([1, 2], [count for _, count in rows])
        self.assertEqual(3, sum(count for _, count in rows))

    def test_rejects_bad_window(self):
        with self.assertRaises(ValueError):
            window_counts([], datetime(2026, 9, 22), datetime(2026, 9, 22, 1), 0)


class PercentileTest(unittest.TestCase):
    def test_empty(self):
        self.assertIsNone(percentile([], 95))

    def test_ten_samples(self):
        self.assertEqual(10, percentile(list(range(1, 11)), 95))

    def test_nearest_rank_twenty_samples(self):
        self.assertEqual(190, percentile(list(range(10, 201, 10)), 95))

    def test_single_sample(self):
        self.assertEqual(7, percentile([7], 95))

    def test_rejects_bad_p(self):
        with self.assertRaises(ValueError):
            percentile([1, 2], 0)


class ByComponentTest(unittest.TestCase):
    def test_sorted_by_p95(self):
        records = [make(1, "api", 100), make(2, "api", 120), make(3, "db", 10)]
        rows = by_component(records)
        self.assertEqual(["api", "db"], [row[0] for row in rows])
        self.assertEqual([2, 1], [row[1] for row in rows])


if __name__ == "__main__":
    unittest.main()
