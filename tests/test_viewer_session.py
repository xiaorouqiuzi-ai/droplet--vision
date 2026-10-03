import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from droplet_vision.annotations import Bookmark, ViewerSession


class SessionTests(unittest.TestCase):
    def test_bookmarks_portable_roundtrip(self):
        session = ViewerSession("sample.cine", 100, 20, 10,
                                [Bookmark(10, 2**62 + 1, .1, "interesting", ["arbitrary_new_tag"])],
                                local_only={"cine_path": str(Path.cwd() / "sample.cine")})
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "session.json"
            session.save(path)
            loaded = ViewerSession.load(path)
            self.assertEqual(loaded.to_dict(), session.to_dict())
            self.assertNotIn("local_only", loaded.to_dict())
            self.assertEqual(loaded.bookmarks[0].timestamp_time64, 2**62 + 1)

    def test_nonportable_paths_rejected(self):
        for name in ("/local/test.cine", "../test.cine", "folder/test.cine"):
            with self.assertRaises(ValueError):
                ViewerSession(name, 10, 1)
        with self.assertRaises(ValueError):
            ViewerSession("test.cine", 10, 1, layer_references=["../unsafe.json"])
        with tempfile.TemporaryDirectory() as temp:
            cine = Path(temp) / 'protected.cine'
            cine.write_bytes(b'original')
            with self.assertRaises(ValueError):
                ViewerSession('test.cine', 10, 1).save(cine)
            self.assertEqual(cine.read_bytes(), b'original')
