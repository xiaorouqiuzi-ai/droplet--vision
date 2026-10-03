"""Pure standard-library tests: synthetic timestamps and tiny tag fragments."""

import io
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from droplet_vision import TimingStatus
from droplet_vision.cine.exceptions import CineFormatError
from droplet_vision.cine.timing import (
    _read_raw_time64, frame_intervals_time64, relative_times_seconds,
    summarize_timing, time64_delta_seconds,
)


class TimingTests(unittest.TestCase):
    def test_integer_precision_and_low_bits(self):
        origin = 2**62
        self.assertEqual(time64_delta_seconds(origin + 1, origin), 1 / 2**32)
        self.assertEqual(time64_delta_seconds(origin, origin + 1), -1 / 2**32)
        self.assertEqual(frame_intervals_time64([origin, origin + 1, origin + 4]), [1, 3])
        self.assertEqual(relative_times_seconds(iter([origin, origin + 1])), [0, 1 / 2**32])

    def test_elapsed_rate_not_mean_inverse(self):
        summary = summarize_timing([0, 2**32, 3 * 2**32], 1)
        self.assertEqual(summary.duration_timestamp_s, 3)
        self.assertAlmostEqual(summary.fps_timestamp, 2 / 3)
        self.assertEqual(summary.interval_mean_s, 1.5)
        self.assertEqual(summary.interval_median_s, 1.5)
        self.assertEqual(summary.interval_std_s, 0.5)
        self.assertEqual(summary.interval_min_s, 1)
        self.assertEqual(summary.interval_max_s, 2)
        self.assertTrue(summary.timestamps_monotonic)
        self.assertEqual(summary.timing_status, TimingStatus.TIMING_MISMATCH_UNRESOLVED)

    def test_agreement_is_not_validation(self):
        for header in (None, 1.0, 1.005):
            summary = summarize_timing([0, 2**32], header)
            self.assertEqual(summary.timing_status, TimingStatus.TIMING_UNKNOWN)
        self.assertEqual(summarize_timing([0, 2**32], 2).fps_ratio, 2)

    def test_duplicates_and_backwards_are_unknown(self):
        summary = summarize_timing([10, 20, 20, 15, 30], 1)
        self.assertEqual(summary.duplicate_timestamp_count, 1)
        self.assertEqual(summary.non_monotonic_count, 1)
        self.assertFalse(summary.timestamps_monotonic)
        self.assertIsNone(summary.fps_timestamp)
        self.assertEqual(summary.timing_status, TimingStatus.TIMING_UNKNOWN)
        self.assertTrue(summary.warnings)

    def test_missing_short_and_count_mismatch(self):
        for raw in ([], [0]):
            summary = summarize_timing(raw, 10)
            self.assertIsNone(summary.fps_timestamp)
            self.assertEqual(summary.timing_status, TimingStatus.TIMING_UNKNOWN)
        summary = summarize_timing([0, 2**32], 2, expected_frame_count=3)
        self.assertIsNone(summary.fps_timestamp)
        self.assertTrue(summary.warnings)
        self.assertEqual(relative_times_seconds([]), [])
        self.assertEqual(frame_intervals_time64([]), [])

    def test_invalid_values(self):
        for threshold in (-1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                summarize_timing([], mismatch_threshold=threshold)
        for value in (-1, 2**64, 1.5):
            with self.assertRaises((ValueError, TypeError)):
                time64_delta_seconds(value, 0)
        summary = summarize_timing([0, 2**32], float('nan'))
        json.dumps(summary.to_dict(), allow_nan=False)


class TagParserTests(unittest.TestCase):
    def parse(self, content, end=None):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'tags.bin'
            path.write_bytes(content)
            return _read_raw_time64(path, 0, 0, len(content) if end is None else end)

    def test_unknown_skip_and_raw_preservation(self):
        unknown = struct.pack('<IHH', 11, 9999, 1) + b'abc'
        payload = struct.pack('<QQ', 2**62 + 1, 2**62 + 7)
        tag = struct.pack('<IHH', 8 + len(payload), 1002, 0) + payload
        self.assertEqual(self.parse(unknown + tag), (2**62 + 1, 2**62 + 7))
        self.assertEqual(self.parse(b''), ())

    def test_bad_bounds_sizes_and_chain(self):
        fragments = [b'abc', struct.pack('<IHH', 0, 1002, 1),
                     struct.pack('<IHH', 7, 1002, 0),
                     struct.pack('<IHH', 16, 1002, 0),
                     struct.pack('<IHH', 9, 1002, 0) + b'x',
                     struct.pack('<IHH', 8, 9999, 1),
                     struct.pack('<IHH', 8, 1002, 1) + struct.pack('<IHH', 8, 1002, 0)]
        for fragment in fragments:
            with self.subTest(fragment=fragment), self.assertRaises(CineFormatError):
                self.parse(fragment)
        with self.assertRaises(CineFormatError):
            self.parse(b'', end=8)

    def test_read_truncation_after_stat(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'tags.bin'
            content = struct.pack('<IHHQ', 16, 1002, 0, 1)
            path.write_bytes(content)
            with patch.object(Path, 'open', return_value=io.BytesIO(content[:-1])):
                with self.assertRaisesRegex(CineFormatError, 'Truncated TIME64'):
                    _read_raw_time64(path, 0, 0, len(content))


if __name__ == '__main__':
    unittest.main()
