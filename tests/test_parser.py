import unittest

from logstats.parser import ParseError, parse_line, parse_lines, parse_timestamp


class ParseTimestampTest(unittest.TestCase):
    def test_naive_timestamp(self):
        moment = parse_timestamp("2026-09-22T00:05:00")
        self.assertEqual((2026, 9, 22, 0, 5, 0), (moment.year, moment.month, moment.day, moment.hour, moment.minute, moment.second))
        self.assertIsNone(moment.tzinfo)

    def test_offset_timestamp_is_converted_to_utc(self):
        moment = parse_timestamp("2026-09-22T09:10:00+08:00")
        self.assertEqual((2026, 9, 22, 1, 10, 0), (moment.year, moment.month, moment.day, moment.hour, moment.minute, moment.second))
        self.assertIsNone(moment.tzinfo)

    def test_z_suffix_is_converted_to_utc(self):
        moment = parse_timestamp("2026-09-22T01:10:00Z")
        self.assertEqual((2026, 9, 22, 1, 10, 0), (moment.year, moment.month, moment.day, moment.hour, moment.minute, moment.second))
        self.assertIsNone(moment.tzinfo)

    def test_bad_timestamp_raises(self):
        with self.assertRaises(ParseError):
            parse_timestamp("not-a-time")


class ParseLineTest(unittest.TestCase):
    def test_fields(self):
        record = parse_line("2026-09-22T00:11:00 WARN [queue] handled in 42ms")
        self.assertEqual("WARN", record.level)
        self.assertEqual("queue", record.component)
        self.assertEqual(42, record.latency_ms)

    def test_bad_line_raises(self):
        with self.assertRaises(ParseError):
            parse_line("2026-09-22T00:11:00 INFO queue handled in 42ms")


class ParseLinesTest(unittest.TestCase):
    def test_skips_blank_and_collects_errors(self):
        records, errors = parse_lines(
            [
                "2026-09-22T00:01:00 INFO [api] handled in 1ms",
                "",
                "这一行不是日志",
                "2026-09-22T00:02:00 INFO [api] handled in 2ms",
            ]
        )
        self.assertEqual(2, len(records))
        self.assertEqual(1, len(errors))
        self.assertEqual(3, errors[0][0])


if __name__ == "__main__":
    unittest.main()
