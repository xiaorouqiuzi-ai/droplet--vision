import json
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from droplet_vision.display import DisplaySettings, render_display
from droplet_vision.display.photometric import (
    MODE, apply_locked_gain, cine_reference_index, default_preset_path,
    estimate_reference, load_photometric_preset)


class PhotometricTests(unittest.TestCase):
    def setUp(self):
        self.preset = load_photometric_preset()

    def test_versioned_json_loader_and_consistency(self):
        self.assertEqual(self.preset.preset_id, 'photometric_ref90_v1')
        self.assertEqual(self.preset.target_p90, 208.8)
        self.assertEqual((self.preset.gain_min, self.preset.gain_max), (.1, 10))
        self.assertEqual((self.preset.saturation_warning_fraction,
                          self.preset.severe_saturation_warning_fraction), (.01, .05))
        self.assertEqual((self.preset.high_gain_warning, self.preset.very_high_gain_warning), (3, 6))
        value = json.loads(default_preset_path().read_text())
        value['target_p90'] += 1
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'invalid.json'
            path.write_text(json.dumps(value))
            with self.assertRaises(ValueError):
                load_photometric_preset(path)

    def test_reference_index(self):
        self.assertEqual(cine_reference_index(32196), round((32196 - 1) * .03))
        self.assertEqual(cine_reference_index(32196), 966)
        self.assertEqual(cine_reference_index(1), 0)
        with self.assertRaises(ValueError):
            cine_reference_index(0)

    def test_gain_and_clipping(self):
        raw = np.full((12, 12), 45, dtype=np.uint8)
        reference = estimate_reference(raw, 100, self.preset)
        self.assertAlmostEqual(reference.gain_used, self.preset.target_p90 / 45)
        np.testing.assert_array_equal(apply_locked_gain(raw, reference), np.full_like(raw, 209))
        high = estimate_reference(np.ones((3, 3), dtype=np.uint8), 100, self.preset)
        self.assertEqual(high.gain_used, self.preset.gain_max)
        self.assertIn('GAIN_CLIPPED_HIGH', high.warnings)
        low = estimate_reference(raw, 100, replace(self.preset, gain_min=5))
        self.assertEqual(low.gain_used, 5)
        self.assertIn('GAIN_CLIPPED_LOW', low.warnings)

    def test_reference_zero_and_unsupported_dtype_rejected(self):
        for image in (np.zeros((2, 2), dtype=np.uint8), np.ones((2, 2), dtype=np.uint16),
                      np.ones((2, 2, 3), dtype=np.uint8)):
            with self.assertRaises(ValueError):
                estimate_reference(image, 100, self.preset)

    def test_saturation_and_high_gain_warnings_are_cumulative(self):
        raw = np.full((10, 10), 30, dtype=np.uint8)
        raw[0, :6] = 255
        result = estimate_reference(raw, 100, self.preset)
        self.assertAlmostEqual(result.norm_255_fraction, .06)
        self.assertTrue({'SATURATION_WARNING', 'SEVERE_SATURATION_WARNING',
                         'HIGH_GAIN_WARNING', 'VERY_HIGH_GAIN_WARNING'} <= set(result.warnings))

    def test_same_locked_gain_preserves_temporal_change_and_raw_memory(self):
        reference = estimate_reference(np.full((8, 8), 45, dtype=np.uint8), 100, self.preset)
        settings = DisplaySettings(mode=MODE, brightness=1, gamma=.2, contrast=4)
        with patch('numpy.percentile', side_effect=AssertionError('Per-frame estimation forbidden')):
            for level in (10, 20):
                raw = np.full((8, 8), level, dtype=np.uint8)
                before = raw.copy()
                raw.setflags(write=False)
                displayed = render_display(raw, settings, photometric=reference).image
                np.testing.assert_array_equal(displayed, np.full_like(raw, round(level * reference.gain_used)))
                np.testing.assert_array_equal(raw, before)
                self.assertFalse(np.shares_memory(raw, displayed))
                self.assertEqual(displayed.shape, raw.shape)
                self.assertEqual(displayed.dtype, np.uint8)


if __name__ == '__main__':
    unittest.main()
