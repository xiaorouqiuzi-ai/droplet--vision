"""Workspace v1.6: display provenance, live language and packaged branding."""
from copy import deepcopy
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import test_ui_annotation_tools as fixture
from test_ui_main_window import QT_AVAILABLE, wait_for

if QT_AVAILABLE:
    from PySide6.QtCore import Qt, QSettings
    from PySide6.QtWidgets import QGraphicsItem, QMessageBox
    from droplet_vision.ui import i18n
    from droplet_vision.ui.branding import ICON_DIRECTORY, REPOSITORY, project_metadata
    from droplet_vision.annotations import ViewerSession
    from droplet_vision.annotations.display_style import record_colors, record_ordinals


@unittest.skipUnless(QT_AVAILABLE, 'Qt unavailable')
class BrandingTests(unittest.TestCase):
    setUpClass = fixture.AnnotationToolsTests.__dict__['setUpClass']
    close_window = fixture.AnnotationToolsTests.close_window
    click = fixture.AnnotationToolsTests.click

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        store = QSettings(str(Path(directory.name)/'language.ini'), QSettings.Format.IniFormat)
        self.store = store
        environment = patch.dict(os.environ, {'DROPLET_VISION_LANGUAGE': 'zh_CN'})
        environment.start(); self.addCleanup(environment.stop)
        patcher = patch.object(i18n, 'preferences', return_value=store)
        patcher.start(); self.addCleanup(patcher.stop)
        fixture.AnnotationToolsTests.setUp(self)
        self.workflow = self.editor.workflow
        self.workflow.apply_scheme()

    def record(self, name='', label='daughter_droplet'):
        self.window.annotation_panel.select_label_id(label)
        self.workflow.instance_name.setText(name)
        self.editor.create_annotation('polygon', {'points':[[20,20],[80,20],[50,70]]})
        return self.editor.document.active_records()[-1]

    def test_palette_badges_list_roundtrip_derived_undo(self):
        records = [self.record('Daughter_01'), self.record('Daughter_07'), self.record()]
        ordinals = record_ordinals(records)
        self.assertEqual([ordinals[r.annotation_id] for r in records], [1,7,2])
        self.assertEqual(ordinals, record_ordinals(list(reversed(records))))
        before = [r.to_dict() for r in records]
        for r in records:
            badge = self.canvas.overlays.badges[r.annotation_id]
            self.assertEqual(badge.data(2), ordinals[r.annotation_id])
            self.assertTrue(badge.flags() & QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
            index = list(records).index(r)
            item = self.window.annotation_panel.items.item(index)
            self.assertIn(f'#{ordinals[r.annotation_id]}', item.text())
            self.assertEqual(badge.brush().color().name().upper(), item.data(Qt.ItemDataRole.UserRole+1))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'annotations.json'
            self.editor.save(path); self.editor.load(path)
        self.assertEqual(before, [r.to_dict() for r in self.editor.document.active_records()])
        self.editor.select(records[0].annotation_id)
        self.editor.rename_selected('Daughter_03')
        renamed = self.editor.selected_record()
        self.assertEqual(self.canvas.overlays.badges[renamed.annotation_id].data(2), 3)
        self.assertEqual(self.canvas.overlays.badges[renamed.annotation_id].brush().color().name().upper(), '#7A6FAC')
        self.editor.undo()
        self.assertEqual(self.canvas.overlays.badges[records[0].annotation_id].data(2), 1)
        self.editor.redo()
        self.assertEqual(self.canvas.overlays.badges[renamed.annotation_id].data(2), 3)
        self.assertEqual(records[0].to_dict(), before[0])

    def test_live_switch_preserves_draft_notes_raw_document_and_selection(self):
        record = self.record('Daughter_02')
        self.editor.switch_tool('select'); self.editor.select(record.annotation_id)
        self.editor.selected_vertex = 1
        self.editor.switch_tool('polygon')
        self.canvas.set_auto_fit(False)
        self.click(100,100); self.click(180,100); self.click(180,180)
        draft = self.editor.tool.draft
        snapshot = draft.snapshot()
        self.workflow.has_note.setChecked(True)
        self.workflow.notes.setPlainText('Manual unsaved note / 人工备注')
        self.workflow.instance_name.setText('Uncommitted name')
        raw = self.window.raw_image.copy()
        document = self.editor.document
        records = [r.to_dict() for r in document.records.records()]
        undo_index = self.editor.undo_stack.index()
        selection = self.editor.selected_id, self.editor.selected_vertex
        frame = self.window.current_record
        for code, parent, state in [('en_US','Parent droplet','Nucleation'), ('zh_CN','父液滴','成核（Nucleation）')]:
            self.window.language_toggle.click()
            self.assertEqual(i18n.current_language(),code)
            self.assertEqual(self.window.annotation_panel.object_buttons['parent_droplet'].text(), parent)
            self.assertEqual(self.workflow.checkboxes['nucleation'].text(), state)
            self.assertEqual(self.workflow.notes.toPlainText(), 'Manual unsaved note / 人工备注')
            self.assertTrue(self.workflow.notes_pending)
            self.assertEqual(self.workflow.instance_name.text(), 'Uncommitted name')
            self.assertIs(self.editor.tool.draft, draft)
            self.assertEqual(draft.snapshot(), snapshot)
            self.assertIs(self.editor.document, document)
            self.assertEqual([r.to_dict() for r in document.records.records()], records)
            self.assertEqual(self.editor.undo_stack.index(), undo_index)
            self.assertEqual((self.editor.selected_id,self.editor.selected_vertex), selection)
            self.assertIs(self.window.current_record,frame)
            np.testing.assert_array_equal(self.window.raw_image,raw)
            self.assertEqual(i18n.preferred_language(self.store),code)

    def test_about_icon_and_language_session_roundtrip(self):
        from PIL import Image
        with Image.open(ICON_DIRECTORY/'planico.png') as image:
            self.assertEqual(image.mode,'RGBA')
            self.assertEqual(image.getchannel('A').getextrema(),(0,255))
        with Image.open(ICON_DIRECTORY/'planico.ico') as icon:
            self.assertIn((256,256),icon.info['sizes'])
        self.assertFalse(self.window.windowIcon().isNull())
        self.assertNotEqual(project_metadata()[0], 'unknown')
        self.window.show_about()
        self.window.change_language('en_US')
        about=self.window.about_dialog
        self.assertIn('xiaorouqiuzi-ai',about.description.text())
        self.assertIn('Author',about.description.text())
        self.assertIn(REPOSITORY, ''.join(w.text() for w in about.findChildren(type(about.description))))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'session.json';self.window.save_session(path)
            session=ViewerSession.load(path)
            self.assertEqual(session.ui_state['language'],'en_US')
            self.window.change_language('zh_CN')
            self.assertIn('作者',about.description.text())
            with patch.object(QMessageBox, 'warning', return_value=QMessageBox.StandardButton.Discard):
                self.window.open_cine('fake.cine',session)
            wait_for(lambda:self.window.current_record is not None)
            self.assertEqual(i18n.current_language(),'en_US')
        about.close()

    def test_custom_scheme_names_order_colors_and_common_states(self):
        scheme=deepcopy(self.workflow.scheme)
        scheme.update(scheme_id='custom_v16',status='custom')
        scheme['display']['object_order'].reverse()
        scheme['display']['object_display_names']['parent_droplet']={'zh_CN':'定制主体','en_US':'Custom parent'}
        scheme['display']['object_styles']['parent_droplet']['color']='#123456'
        scheme['display']['common_frame_states']=['nucleation']
        self.workflow.scheme_selector.addItem('custom',scheme)
        self.workflow.scheme_selector.setCurrentIndex(1)
        self.workflow.apply_scheme()
        self.window.change_language('en_US')
        panel=self.window.annotation_panel
        self.assertEqual(list(panel.object_buttons)[0],'soot')
        self.assertEqual(panel.object_buttons['parent_droplet'].text(),'Custom parent')
        self.assertNotIn('nucleation',self.workflow.more_actions)
        self.assertIn('simple_evaporation',self.workflow.more_actions)
        record=self.record('Parent_01','parent_droplet')
        self.assertEqual(self.canvas.overlays.by_id[record.annotation_id].data(1),'#123456')
        self.window.change_language('zh_CN')
        self.assertEqual(panel.object_buttons['parent_droplet'].text(),'定制主体')
