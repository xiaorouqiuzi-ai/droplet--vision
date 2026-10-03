import subprocess
import sys
import unittest
from unittest.mock import patch
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from droplet_vision.display import (DisplaySettings, DisplayResult, apply_display_transform,
                                   render_display, register_display_mode, display_modes)


class DisplayTransformTests(unittest.TestCase):
    def test_raw_identity_independent_array(self):
        image = np.arange(256, dtype=np.uint8).reshape(16, 16)
        result = apply_display_transform(image, DisplaySettings(brightness=.9, gamma=.2))
        np.testing.assert_array_equal(result, image)
        self.assertFalse(np.shares_memory(result, image))
        result[:] = 0
        self.assertEqual(image[-1, -1], 255)

    def test_manual_formula(self):
        image = np.array([[0, 64, 128, 192, 255]], dtype=np.uint8)
        for kwargs, expected in [({}, image), ({'brightness': .25}, [[64, 128, 192, 255, 255]]),
                                 ({'contrast': 2}, [[0, 0, 128, 255, 255]]),
                                 ({'gamma': .5}, [[0, 128, 181, 221, 255]])]:
            with self.subTest(kwargs=kwargs):
                np.testing.assert_array_equal(apply_display_transform(image, DisplaySettings(mode='manual', **kwargs)), expected)
        settings = DisplaySettings(mode='manual', brightness=.1, contrast=1.4, gamma=.7)
        expected = np.rint(np.clip((image.astype(float)/255 - .5)*1.4 + .5 + .1, 0, 1)**.7 * 255).astype(np.uint8)
        np.testing.assert_array_equal(apply_display_transform(image, settings), expected)

    def test_percentile_clipping_and_narrow_range(self):
        image = np.array([[0, 10, 20, 30, 40]], dtype=np.uint8)
        settings = DisplaySettings(mode='auto_percentile', percentile_low=25, percentile_high=75)
        np.testing.assert_array_equal(apply_display_transform(image, settings), [[0, 0, 128, 255, 255]])
        narrow = np.array([[100, 101]], dtype=np.uint8)
        np.testing.assert_array_equal(apply_display_transform(narrow, DisplaySettings(mode='auto_percentile')), [[0, 255]])

    def test_constant_zero_and_degenerate_percentiles(self):
        for value in (0, 77, 255):
            image = np.full((5, 5), value, dtype=np.uint8)
            result = render_display(image, DisplaySettings(mode='auto_percentile'))
            np.testing.assert_array_equal(result.image, image)
            self.assertIn('Insufficient', result.diagnostic)
        image = np.zeros((100, 100), dtype=np.uint8)
        image[0, 0] = 255
        self.assertTrue(render_display(image, DisplaySettings(mode='auto_percentile')).diagnostic)

    def test_input_immutability_shape_dtype_and_determinism(self):
        for image in (np.arange(256, dtype=np.uint8).reshape(16, 16)[:, ::2],
                      np.arange(60, dtype=np.uint8).reshape(4, 5, 3),
                      np.array([[0, 100, 256, 65535]], dtype=np.uint16)):
            before = image.copy()
            image.setflags(write=False)
            for mode in ('raw', 'manual', 'auto_percentile'):
                settings = DisplaySettings(mode=mode, brightness=.25, contrast=1.4, gamma=.7)
                first = apply_display_transform(image, settings)
                np.testing.assert_array_equal(image, before)
                np.testing.assert_array_equal(first, apply_display_transform(image, settings))
                self.assertEqual(image.dtype, before.dtype)
                self.assertEqual(first.shape, image.shape)
                self.assertEqual(first.dtype, np.uint8)
                self.assertFalse(np.shares_memory(first, image))
        np.testing.assert_array_equal(apply_display_transform(image, DisplaySettings()), [[0, 0, 1, 255]])

    def test_invalid_image_and_unavailable_backend(self):
        for image in (np.empty((0, 2), dtype=np.uint8), np.zeros((2, 2), dtype=float),
                      np.zeros((2, 2, 4), dtype=np.uint8)):
            with self.assertRaises(ValueError):
                apply_display_transform(image, DisplaySettings())
        with self.assertRaises(ValueError):
            apply_display_transform(np.zeros((1, 1), dtype=np.uint8), DisplaySettings(mode='missing'))

    def test_import_and_transform_without_qt(self):
        source = str(Path(__file__).resolve().parents[1] / 'src')
        code = ("import sys; sys.path.insert(0, " + repr(source) + "); "
                "sys.modules['PySide6'] = None; "
                "import numpy as np; from droplet_vision.display import DisplaySettings, apply_display_transform; "
                "assert apply_display_transform(np.zeros((2,2),dtype=np.uint8),DisplaySettings()).shape == (2,2)")
        subprocess.run([sys.executable, '-B', '-c', code], check=True, capture_output=True)

    def test_extension_receives_copy(self):
        from droplet_vision.display import transforms
        def extension(image, settings):
            image[:] = 42
            return DisplayResult(image)
        with patch.dict(transforms._MODES):
            register_display_mode('test_extension', 'Test extension', extension)
            raw = np.zeros((2, 2), dtype=np.uint8)
            np.testing.assert_array_equal(apply_display_transform(raw, DisplaySettings(mode='test_extension')), 42)
            np.testing.assert_array_equal(raw, 0)
            self.assertIn('test_extension', display_modes())
