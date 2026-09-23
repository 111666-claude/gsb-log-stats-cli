import random
import unittest

from logstats.stats import Histogram, percentile


class HistogramTest(unittest.TestCase):
    def test_empty_percentile_is_none(self):
        self.assertIsNone(Histogram().percentile(95))

    def test_count_and_estimate_within_bound(self):
        hist = Histogram()
        for value in range(10, 201, 10):
            hist.add(value)
        self.assertEqual(20, hist.count)
        estimate = hist.percentile(95)
        self.assertAlmostEqual(190, estimate, delta=hist.error_bound)

    def test_bucket_count_never_exceeds_limit(self):
        hist = Histogram(max_buckets=8)
        for value in range(1000):
            hist.add(value)
            self.assertLessEqual(len(hist.buckets), 8)
        self.assertEqual(1000, hist.count)

    def test_error_bound_grows_with_width(self):
        hist = Histogram(max_buckets=8)
        hist.add(0)
        self.assertEqual(0.5, hist.error_bound)
        for value in range(1000):
            hist.add(value)
        self.assertGreater(hist.error_bound, 0.5)
        estimate = hist.percentile(95)
        exact = percentile(list(range(1000)), 95)
        self.assertAlmostEqual(exact, estimate, delta=hist.error_bound)

    def test_estimate_within_bound_on_random_data(self):
        rng = random.Random(42)
        values = [rng.randrange(0, 100000) for _ in range(5000)]
        hist = Histogram(max_buckets=64)
        for value in values:
            hist.add(value)
        self.assertLessEqual(len(hist.buckets), 64)
        for p in (50, 95, 99):
            self.assertAlmostEqual(percentile(values, p), hist.percentile(p), delta=hist.error_bound)

    def test_rejects_negative_value(self):
        with self.assertRaises(ValueError):
            Histogram().add(-1)

    def test_rejects_bad_bucket_limit(self):
        with self.assertRaises(ValueError):
            Histogram(max_buckets=0)


if __name__ == "__main__":
    unittest.main()
