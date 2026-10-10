import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import time
from threading import Event
import unittest
from unittest.mock import patch

from PySide6.QtCore import QSettings, QTimer, QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox
from test_batch_annotation_package import SyntheticReader
from droplet_vision.annotations.scheme import load_scheme
from droplet_vision.ui import i18n
from droplet_vision.ui.batch_package import BatchPackageDialog
from droplet_vision.ui.main_window import MainWindow


class BatchDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root/'A'; self.source.mkdir()
        (self.source/'one.cine').write_text('100')
        self.settings = QSettings(str(self.root/'settings.ini'), QSettings.Format.IniFormat)
        for target, value in [('droplet_vision.review_package.cine_export.CineReader', SyntheticReader),
                              ('droplet_vision.ui.i18n.preferences', None)]:
            p = patch(target, value) if value else patch(target, return_value=self.settings)
            p.start(); self.addCleanup(p.stop)
        self.d = BatchPackageDialog(load_scheme())
        self.d.source.setText(str(self.source))
        self.d.output.setText(str(self.root/'Packages'))
        self.d.show()
        self.addCleanup(self.close_dialog)

    def wait(self):
        end = time.monotonic()+15
        while self.d.busy and time.monotonic() < end:
            self.app.processEvents(); QTest.qWait(5)
        self.assertFalse(self.d.busy)

    def close_dialog(self):
        self.d.cancel_event.set()
        self.wait()
        self.d.close()
        self.d.pool.waitForDone()
        self.d.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_scan_preview_start_progress_summary_and_resume(self):
        d = self.d
        self.assertEqual((d.samples.value(), d.context.value(), d.policy.currentData()), (20, 0, 'skip'))
        self.assertFalse(d.start_button.isEnabled())
        d.scan_button.click(); self.wait()
        self.assertEqual(d.table.rowCount(), 1)
        self.assertEqual(d.table.item(0, 1).text(), 'one.cine')
        self.assertEqual(d.table.item(0, 2).text(), '100')
        self.assertEqual(d.table.item(0, 3).text(), '20')
        self.assertTrue(d.start_button.isEnabled())
        d.start_button.click(); self.wait()
        self.assertEqual(d.result_data.created, 1)
        self.assertTrue(d.open_output.isEnabled())
        self.assertEqual(d.frames.value(), 21)
        d.scan(); self.wait(); d.start(); self.wait()
        self.assertEqual(d.result_data.skipped, 1)
        d.samples.setValue(3)
        self.assertIsNone(d.plan)
        self.assertFalse(d.start_button.isEnabled())

    def test_cancel_during_read_ui_responsive(self):
        d = self.d
        d.scan(); self.wait()
        entered, release = Event(), Event()
        original = SyntheticReader.read_frame
        def slow(reader, index):
            entered.set()
            release.wait(5)
            return original(reader, index)
        timer_ticks = []
        timer = QTimer(d); timer.setInterval(1)
        timer.timeout.connect(lambda: timer_ticks.append(1)); timer.start()
        with patch.object(SyntheticReader, 'read_frame', slow):
            d.start()
            try:
                end = time.monotonic()+5
                while not entered.is_set() and time.monotonic() < end:
                    self.app.processEvents(); QTest.qWait(5)
                self.assertTrue(entered.is_set())
                self.assertTrue(timer_ticks)
                d.cancel_button.click()
                self.assertTrue(d.busy)
                d.close()
                self.assertTrue(d.isVisible())
            finally:
                release.set()
            self.wait()
        timer.stop()
        self.assertTrue(d.result_data.cancelled)
        self.assertFalse((self.root/'Packages/A/one.dvapkg').exists())

    def test_invalid_output_warns_and_does_not_write(self):
        self.d.output.setText(str(self.source/'packages'))
        with patch.object(QMessageBox, 'warning') as warning:
            self.d.scan(); self.wait()
        warning.assert_called_once()
        self.assertIsNone(self.d.plan)
        self.assertFalse((self.source/'packages').exists())

    def test_functions_entry_scheme_snapshot_and_live_language(self):
        w = MainWindow()
        try:
            w.review_manager.batch_dialog()
            dialog = w.review_manager.batch_window
            self.assertEqual(dialog.scheme, w.editor.workflow.scheme)
            self.assertIsNot(dialog.scheme, w.editor.workflow.scheme)
            for language in ('en_US', 'zh_CN'):
                w.change_language(language)
                self.assertEqual(dialog.windowTitle(), i18n.tr('Batch Annotation Packages from Folder'))
                self.assertEqual(dialog.scan_button.text(), i18n.tr('Scan'))
                self.assertIn(i18n.tr('Create Annotation Packages from Folder...'),
                              [a.text() for a in w.functions_menu.actions()])
            dialog.close()
        finally:
            w.close()
            w.deleteLater()
            self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
