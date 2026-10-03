import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from droplet_vision.ui.frame_cache import FrameCache


class CacheTests(unittest.TestCase):
    def test_eviction_uses_recency(self):
        cache = FrameCache(2)
        cache.put(0, 'a')
        cache.put(1, 'b')
        self.assertEqual(cache.get(0), 'a')
        cache.put(2, 'c')
        self.assertIsNone(cache.get(1))
        self.assertEqual(len(cache), 2)
        cache.clear()
        self.assertEqual(len(cache), 0)
