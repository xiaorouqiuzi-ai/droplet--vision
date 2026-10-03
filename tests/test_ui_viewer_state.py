import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from droplet_vision.ui.viewer_state import ViewerState


class StateTests(unittest.TestCase):
    def test_clamp_and_stale_tokens(self):
        state = ViewerState(frame_count=20)
        old = state.request(100)
        self.assertEqual(state.frame_index, 19)
        current = state.request(-5)
        self.assertEqual(state.frame_index, 0)
        self.assertFalse(state.accepts(old))
        self.assertTrue(state.accepts(current))
        self.assertEqual(state.playback_fps, 10)
