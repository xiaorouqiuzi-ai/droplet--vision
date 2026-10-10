import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from copy import deepcopy
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QSettings
from test_uniform_annotation_package import empty_package
import test_ui_layout as layout_tests
from droplet_vision.ui import i18n
from droplet_vision.ui.main_window import MainWindow
from droplet_vision.review_package import AnnotationPackage


class PackageScopeUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        settings = QSettings(str(Path(self.tmp.name)/'settings.ini'),QSettings.Format.IniFormat)
        p = patch.object(i18n,'preferences',return_value=settings);p.start();self.addCleanup(p.stop)
        self.window = MainWindow();self.window.show()
        self.addCleanup(self.close)
        _, _, self.package = empty_package(samples=20)
        self.path=Path(self.tmp.name)/'rods.dvapkg';self.package.save(self.path)
        self.window.review_manager.open(self.package,'Scope tester')
        self.editor=self.window.editor;self.panel=self.editor.workflow.support_template
        self.list=self.window.annotation_panel
        self.list.select_label_id('support_structure')

    def close(self):
        with patch.object(QMessageBox,'warning',return_value=QMessageBox.StandardButton.Discard): self.window.close()

    def rods(self):
        self.window.navigate(99)
        for x in (5,10):
            self.assertTrue(self.editor.create_annotation('polygon',{'points':[[x,5],[x+1,5],[x+1,12],[x,12]]}))
        doc=self.editor.document
        key=doc.active_records(99)[0].annotation_id
        actions=self.list.context_menu(key).actions()
        action=next(a for a in actions if a.text()==i18n.tr('Set as support-rod template and apply to entire package'))
        action.trigger()
        self.assertTrue(self.panel.apply.isChecked())
        self.editor.switch_tool('select')
        return doc

    def drag(self,dx,dy):
        mover=self.editor.support_move
        self.editor.refresh_selection()
        self.assertIsNotNone(mover.item)
        start=mover.item.pos();start=(start.x(),start.y())
        self.editor.tool.mouse_press(start)
        self.editor.tool.mouse_move((start[0]+dx,start[1]+dy))
        self.editor.tool.mouse_release((start[0]+dx,start[1]+dy))

    def test_scope_checkbox_context_menu_replace_confirmation_and_live_language(self):
        self.assertFalse(self.panel.apply.isEnabled())
        self.assertEqual(self.panel.apply.text(),i18n.tr('Apply to entire package'))
        self.list.select_label_id('parent_droplet');self.assertTrue(self.panel.isHidden())
        self.list.select_label_id('support_structure')
        doc=self.rods()
        before=doc.package_templates
        key=doc.active_records(99)[0].annotation_id
        with patch.object(self.panel,'confirm_replace',return_value=False) as confirm:
            self.panel.set_template(apply=True,confirm=True)
            confirm.assert_called_once()
        self.assertEqual(doc.package_templates,before)
        with patch.object(self.panel,'confirm_replace',return_value=True): self.panel.set_template(apply=True,confirm=True)
        self.window.navigate(0)
        projection=next(iter(self.editor.projections()))
        menu=self.list.context_menu(projection)
        self.assertNotIn(i18n.tr('Delete Annotation'),[a.text() for a in menu.actions()])
        self.assertIn(i18n.tr('Disable package-wide application'),[a.text() for a in menu.actions()])
        self.assertIn(i18n.tr('Package template'),self.list.items.item(0).text())
        for language in ('en_US','zh_CN'):
            self.window.change_language(language)
            self.assertEqual(self.panel.apply.text(),i18n.tr('Apply to entire package'))
        self.panel.apply.click();self.assertFalse(self.editor.projections())
        self.editor.undo();self.assertEqual(len(self.editor.projections()),2)

    def test_move_sparse_quick_save_reload_undo_markers_and_raw_unchanged(self):
        doc=self.rods();source=deepcopy(doc.package_templates)
        raw=deepcopy(self.package.frames);metadata=deepcopy(self.package.manifest['frames'])
        self.window.navigate(0);self.drag(2,-1)
        self.window.navigate(5);self.drag(-4,3)
        self.assertEqual(len(doc.records.records()),2)
        self.assertEqual(self.window.timeline.slider.marked_frames,{0,5,99})
        self.assertEqual(self.package.progress(doc.cine_id),(20,3,17))
        self.window.navigate(10);self.assertEqual(doc.support_translation(10),{'dx':0,'dy':0})
        self.assertTrue(self.window.review_manager.quick_save())
        self.assertTrue(self.window.transport.save_package.isHidden())
        expected=doc.package_templates
        loaded=AnnotationPackage.open(self.path)
        self.assertEqual(loaded.documents[doc.cine_id].package_templates,expected)
        self.assertEqual(loaded.frames,raw);self.assertEqual(loaded.manifest['frames'],metadata)
        self.window.review_manager.open(loaded,'Tester')
        self.list.select_label_id('support_structure');self.editor.switch_tool('select');self.window.navigate(5)
        self.drag(1,0);self.assertFalse(self.window.transport.save_package.isHidden())
        self.editor.undo();self.assertTrue(self.window.transport.save_package.isHidden())
        self.editor.redo();self.assertFalse(self.window.transport.save_package.isHidden())
        self.assertEqual(expected['support_structure']['annotation_ids'],source['support_structure']['annotation_ids'])

    def test_vertex_materializes_frame_group_delete_falls_back_and_reset(self):
        doc=self.rods();self.window.navigate(0);self.drag(2,-1)
        projection=next(iter(self.editor.projections().values()))
        geometry=deepcopy(projection.geometry);geometry['points'][0][0]+=.25
        self.assertTrue(self.editor.edit_annotation(projection.annotation_id,geometry))
        self.assertEqual(doc.support_translation(0),{'dx':0,'dy':0})
        self.assertEqual(len(doc.support_copies(0)),2)
        self.assertTrue(all(r.attributes['creation_tool']=='package_support_template_override' for r in doc.support_copies(0)))
        for row in list(doc.support_copies(0)): self.editor.delete_record(row.annotation_id)
        self.assertEqual(len(self.editor.projections()),2)
        self.window.navigate(5);self.drag(1,1)
        key=next(iter(self.editor.projections()))
        reset=next(a for a in self.list.context_menu(key).actions() if a.text()==i18n.tr('Reset frame position'))
        self.assertTrue(reset.isEnabled());reset.trigger()
        self.assertEqual(doc.support_translation(5),{'dx':0,'dy':0})
        self.assertEqual(self.window.timeline.slider.marked_frames,{99})


class CineScopeContextTests(unittest.TestCase):
    setUpClass=layout_tests.LayoutTests.__dict__['setUpClass']
    setUp=layout_tests.LayoutTests.setUp
    close_window=layout_tests.LayoutTests.close_window

    def test_cine_menu_scope_and_non_support_exclusion(self):
        panel=self.editor.workflow.support_template
        self.window.annotation_panel.select_label_id('support_structure')
        self.editor.create_annotation('polygon',{'points':[[10,10],[15,10],[15,30]]})
        record=self.editor.document.active_records()[0]
        menu=self.window.annotation_panel.context_menu(record.annotation_id)
        action=next(a for a in menu.actions() if a.text()==i18n.tr('Set as support-rod template and apply to entire Cine'))
        action.trigger()
        self.assertTrue(panel.apply.isChecked())
        self.assertEqual(panel.apply.text(),i18n.tr('Apply to entire Cine'))
        self.assertEqual(self.editor.document.package_templates,{})
        self.window.annotation_panel.select_label_id('parent_droplet')
        self.editor.create_annotation('polygon',{'points':[[30,30],[40,30],[40,40]]})
        record=self.editor.document.active_records()[-1]
        self.assertFalse(any('template' in a.text().lower() or '模板' in a.text() for a in self.window.annotation_panel.context_menu(record.annotation_id).actions()))
