"""Reader contract tests without PIMS, NumPy or real Cine data."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from droplet_vision.cine import CineReader
from droplet_vision.cine.exceptions import CineDependencyError
from droplet_vision.cine.metadata import CineMetadata
from droplet_vision import TimingStatus


class ReaderTests(unittest.TestCase):
    def test_import_without_site_packages(self):
        source = str(Path(__file__).resolve().parents[1] / 'src')
        code = ('import sys; sys.path.insert(0, ' + repr(source) + '); '
                'import droplet_vision; import droplet_vision.cine; '
                'assert "pims" not in sys.modules; assert "numpy" not in sys.modules')
        subprocess.run([sys.executable, '-S', '-c', code], check=True, capture_output=True)

    def test_missing_file_and_missing_dependency(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.cine'
            with self.assertRaises(FileNotFoundError):
                CineReader(path)
            path.touch()
            with patch.dict(sys.modules, {'pims': None}):
                with self.assertRaisesRegex(CineDependencyError, "optional 'cine'"):
                    CineReader(path)

    def test_failure_closes_backend(self):
        from unittest.mock import MagicMock
        backend = MagicMock()
        backend._raw_time64 = ()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.cine'
            path.touch()
            with patch('droplet_vision.cine.reader._open_backend', return_value=backend):
                with patch('droplet_vision.cine.reader._extract_metadata', side_effect=ValueError):
                    with self.assertRaises(ValueError):
                        CineReader(path)
            backend.close.assert_called_once()

    def test_backend_init_failure_closes_handle(self):
        class BrokenCine:
            def __init__(self, filename):
                self.f = open(filename, 'rb')
                handles.append(self.f)
                raise ValueError('bad header')
        handles = []
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.cine'
            path.touch()
            with patch.dict(sys.modules, {'pims': SimpleNamespace(Cine=BrokenCine)}):
                with self.assertRaises(ValueError):
                    CineReader(path)
        self.assertTrue(handles[0].closed)

    def test_metadata_only_shape_and_frame_record_without_pixels(self):
        from unittest.mock import MagicMock
        backend = MagicMock()
        backend.__len__.return_value = 2
        backend._raw_time64 = (2**62, 2**62 + 2**32)
        backend.pixel_type = 'uint8'
        metadata = CineMetadata(width=12, height=8, cfa=0, fps_header=2, compression=0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.cine'
            path.touch()
            with patch('droplet_vision.cine.reader._open_backend', return_value=backend):
                with patch('droplet_vision.cine.reader._extract_metadata', return_value=metadata):
                    with CineReader(path) as reader:
                        self.assertEqual(reader.frame_shape, (8, 12))
                        self.assertEqual(reader.build_frame_result(1).timestamp_s, 1)
                        self.assertEqual(reader.build_frame_result(1).timing_status,
                                         TimingStatus.TIMING_MISMATCH_UNRESOLVED)
                        backend._get_frame.assert_not_called()
            backend.close.assert_called_once()

    def test_missing_and_invalid_timestamp_mapping_has_no_fps_fallback(self):
        from unittest.mock import MagicMock
        for raw in ((), (1,), (20, 10)):
            backend = MagicMock()
            backend.__len__.return_value = 2
            backend._raw_time64 = raw
            metadata = CineMetadata(width=12, height=8, cfa=0, fps_header=100)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'test.cine'
                path.touch()
                with patch('droplet_vision.cine.reader._open_backend', return_value=backend):
                    with patch('droplet_vision.cine.reader._extract_metadata', return_value=metadata):
                        with CineReader(path) as reader:
                            record = reader.build_frame_result(1)
                            self.assertIsNone(record.timestamp_s)
                            self.assertEqual(record.timing_status, TimingStatus.TIMING_UNKNOWN)
                            self.assertEqual(record.timestamp_time64, 10 if len(raw) == 2 else None)


if __name__ == '__main__':
    unittest.main()
