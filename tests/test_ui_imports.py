import sys
import subprocess
import unittest
from pathlib import Path


class ImportTests(unittest.TestCase):
    def test_core_is_free_of_qt_models_and_site_packages(self):
        source = str(Path(__file__).resolve().parents[1] / 'src')
        code = ("import sys; sys.path.insert(0, " + repr(source) + "); "
                "import droplet_vision, droplet_vision.cine, droplet_vision.annotations, droplet_vision.inference; "
                "assert not any(k in sys.modules for k in ('PySide6', 'pims', 'torch', 'ultralytics'))")
        subprocess.run([sys.executable, '-S', '-B', '-c', code], check=True, capture_output=True)
