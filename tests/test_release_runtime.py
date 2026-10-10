"""Release entry and resource resolution, without changing scientific behaviour."""
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from droplet_vision import resources
from droplet_vision._version import __version__, DISPLAY_VERSION, WINDOWS_VERSION


class ReleaseRuntimeTests(unittest.TestCase):
    def test_source_resources_independent_of_working_directory(self):
        original = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                self.assertTrue(resources.resource_path('configs/annotations/frame_state_v1.json').is_file())
                self.assertTrue(resources.ui_resource_path('assets/icons/planico.ico').is_file())
                self.assertEqual(resources.output_path('annotations'), Path('outputs/annotations'))
            finally:
                os.chdir(original)

    def test_frozen_resource_and_writable_locations(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            with patch.object(sys, 'frozen', True, create=True), patch.object(sys, '_MEIPASS', str(base/'bundle'), create=True), patch.dict(os.environ, {'LOCALAPPDATA': str(base/'user')}):
                self.assertEqual(resources.resource_path('configs'), base/'bundle/configs')
                self.assertEqual(resources.ui_resource_path('translations'), base/'bundle/droplet_vision/ui/translations')
                self.assertEqual(resources.output_path('annotations'), base/'user/DropletVision/annotations')

    def test_single_version_formats(self):
        from packaging.version import Version
        self.assertEqual(str(Version(DISPLAY_VERSION)), __version__)
        self.assertEqual(WINDOWS_VERSION, (0, 1, 0, 1))

    def test_file_dispatch_unicode_case_and_legacy(self):
        from droplet_vision.ui.app import open_startup_file
        window = Mock()
        path = '实验 数据/测试.CiNe'
        open_startup_file(window, path)
        window.open_cine.assert_called_once_with(path)
        package = Mock(review={})
        with patch('droplet_vision.review_package.ReviewPackage.open', return_value=package) as reader:
            for path in ('实验 数据/测试.DVAPKG', '实验 数据/旧包.DvRpKg'):
                open_startup_file(window, path)
                reader.assert_called_with(path)
                window.review_manager.open.assert_called_with(package, '')
        window._error.assert_not_called()

    def test_unknown_and_corrupt_files_are_friendly_errors(self):
        from droplet_vision.ui.app import open_startup_file
        window = Mock()
        open_startup_file(window, 'unknown.txt')
        window._error.assert_called_once()
        window.open_cine.assert_not_called()
        window.review_manager.open.assert_not_called()
        with patch('droplet_vision.review_package.ReviewPackage.open', side_effect=ValueError('Invalid package')):
            open_startup_file(window, 'broken.dvapkg')
        window._error.assert_called_with('Invalid package')
