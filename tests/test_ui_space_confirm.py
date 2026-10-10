"""Real Qt key dispatch: draft ownership, text focus and single-action semantics."""
import unittest
from unittest.mock import patch
import test_ui_interaction as fixture
from test_ui_main_window import QT_AVAILABLE

if QT_AVAILABLE:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QLineEdit, QPushButton


@unittest.skipUnless(QT_AVAILABLE, 'Qt unavailable')
class SpaceConfirmTests(unittest.TestCase):
    setUpClass = classmethod(fixture.DraftTests.setUpClass.__func__)
    setUp = fixture.DraftTests.setUp
    close_window = fixture.DraftTests.close_window
    click = fixture.DraftTests.click
    drag = fixture.DraftTests.drag
    polygon = fixture.DraftTests.polygon
    wand = fixture.DraftTests.wand

    def key(self, key=None):
        key = Qt.Key.Key_Space if key is None else key
        self.window.activateWindow()
        self.canvas.setFocus()
        QTest.qWait(1)
        QTest.keyClick(self.canvas, key)

    def test_closed_space_exactly_one_record_and_undo_redo(self):
        self.polygon(True)
        with patch.object(self.window, 'toggle_play') as play:
            self.key()
            play.assert_not_called()
        self.assertEqual(len(self.editor.document.records.records()), 1)
        self.assertEqual(len(self.editor.document.active_records()), 1)
        self.assertEqual(self.editor.undo_stack.count(), 1)
        self.editor.undo()
        self.assertFalse(self.editor.document.active_records())
        self.editor.redo()
        self.assertEqual(len(self.editor.document.active_records()), 1)

    def test_open_space_neither_closes_nor_plays_and_esc_cancels(self):
        draft = self.polygon()
        with patch.object(self.window, 'toggle_play') as play:
            self.key()
            play.assert_not_called()
        self.assertFalse(draft.closed)
        self.assertFalse(self.editor.document.active_records())
        self.assertTrue(self.window.statusBar().currentMessage())
        self.key(Qt.Key.Key_Escape)
        self.assertFalse(draft.active)

    def test_no_draft_play_pause_and_persisted_selection(self):
        self.editor.switch_tool('select')
        self.key()
        self.assertTrue(self.window.playback.isActive())
        self.key()
        self.assertFalse(self.window.playback.isActive())
        self.polygon(True)
        self.key()
        self.assertIsNotNone(self.editor.selected_record())
        self.key()
        self.assertTrue(self.window.playback.isActive())
        self.key()
        self.assertFalse(self.window.playback.isActive())

    def test_wand_multiple_components_space_compound_confirm(self):
        self.wand()
        self.editor.wand_panel.mode.setCurrentIndex(1)
        self.click(105,105)
        self.assertEqual(len(self.editor.tool.draft.polygons), 2)
        self.key()
        self.assertEqual(len(self.editor.document.active_records()), 2)
        self.assertEqual(self.editor.undo_stack.count(), 1)
        self.editor.undo()
        self.assertFalse(self.editor.document.active_records())
        self.editor.redo()
        self.assertEqual(len(self.editor.document.active_records()), 2)

    def test_enter_still_confirms(self):
        self.polygon(True)
        self.key(Qt.Key.Key_Return)
        self.assertEqual(len(self.editor.document.active_records()), 1)

    def test_text_focus_keeps_space_with_and_without_draft(self):
        line = QLineEdit(self.window)
        line.show()
        notes = self.editor.workflow.notes
        notes.show()
        for closed in (False, True):
            if closed:
                self.polygon(True)
            for widget in (notes, line):
                widget.setFocus()
                QTest.qWait(1)
                with patch.object(self.window, 'toggle_play') as play:
                    QTest.keyClick(widget, Qt.Key.Key_Space)
                    play.assert_not_called()
                self.assertFalse(self.editor.document.active_records())
        self.assertEqual(line.text(), '  ')
        self.assertEqual(notes.toPlainText(), '  ')

    def test_focused_button_only_native_action(self):
        self.polygon(True)
        button = QPushButton('Native', self.window)
        button.show()
        clicked = []
        button.clicked.connect(lambda: clicked.append(True))
        button.setFocus()
        QTest.qWait(1)
        with patch.object(self.window, 'toggle_play') as play:
            QTest.keyClick(button, Qt.Key.Key_Space)
            play.assert_not_called()
        self.assertEqual(clicked, [True])
        self.assertFalse(self.editor.document.active_records())
        confirm = self.editor.tool_settings.confirm_button
        confirm.setFocus()
        QTest.qWait(1)
        QTest.keyClick(confirm, Qt.Key.Key_Space)
        self.assertEqual(len(self.editor.document.records.records()), 1)

    def test_live_language_hint_and_no_autorepeat(self):
        from droplet_vision.ui.i18n import set_language
        self.polygon(True)
        try:
            for language, expected in [('zh_CN', '空格'), ('en_US', 'Space')]:
                set_language(language)
                self.editor.tool_settings.show_tool('polygon')
                self.assertIn(expected, self.editor.tool_settings.hint.text())
            self.assertFalse(self.window.space_shortcut.autoRepeat())
        finally:
            set_language('en_US')

    def test_package_without_draft_retains_playback_dispatch(self):
        from test_uniform_annotation_package import empty_package
        _, _, package = empty_package()
        self.assertTrue(self.window.review_manager.open(package, 'Shortcut test'))
        with patch.object(self.window, 'toggle_play') as play:
            self.key()
            play.assert_called_once()

    def test_invalid_wand_draft_does_not_play_or_commit(self):
        self.wand()
        self.editor.tool.valid = False
        with patch.object(self.window, 'toggle_play') as play:
            self.key()
            play.assert_not_called()
        self.assertFalse(self.editor.document.active_records())
