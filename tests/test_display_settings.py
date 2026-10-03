import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from droplet_vision.display import DisplaySettings


class DisplaySettingsTests(unittest.TestCase):
    def test_defaults_roundtrip_and_open_mode_id(self):
        settings = DisplaySettings()
        self.assertEqual(settings.mode, 'raw')
        self.assertEqual(DisplaySettings.from_dict(json.loads(json.dumps(settings.to_dict()))), settings)
        self.assertEqual(DisplaySettings(mode='future_backend').mode, 'future_backend')

    def test_invalid_parameters(self):
        for value in ({'gamma': 0}, {'gamma': -1}, {'gamma': float('nan')},
                      {'gamma': float('inf')}, {'gamma': True}, {'contrast': 0},
                      {'brightness': 1.1}, {'brightness': 'bright'}, {'mode': ''},
                      {'percentile_low': -1}, {'percentile_high': 101},
                      {'percentile_low': 99, 'percentile_high': 1},
                      {'percentile_low': 50, 'percentile_high': 50}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                DisplaySettings(**value)
