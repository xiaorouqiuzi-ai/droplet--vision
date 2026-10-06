import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
import test_ui_annotation_tools as tools_fixture
from test_ui_main_window import wait_for, QT_AVAILABLE

if QT_AVAILABLE:
    from PySide6.QtCore import Qt, QPointF, QSettings
    from PySide6.QtWidgets import QApplication, QMessageBox
    from PySide6.QtTest import QTest
    from droplet_vision.ui.main_window import MainWindow
    from droplet_vision.ui.cine_controller import CineController
    from droplet_vision.ui import i18n


@unittest.skipUnless(QT_AVAILABLE,'Qt unavailable')
class VertexTests(unittest.TestCase):
    setUpClass=classmethod(tools_fixture.AnnotationToolsTests.setUpClass.__func__)
    setUp=tools_fixture.AnnotationToolsTests.setUp
    close_window=tools_fixture.AnnotationToolsTests.close_window
    click=tools_fixture.AnnotationToolsTests.click
    drag=tools_fixture.AnnotationToolsTests.drag

    def polygon(self):
        self.editor.create_annotation('polygon',{'points':[[20,20],[100,20],[100,100],[20,100]]})
        self.editor.switch_tool('select')  # Label selection now recommends a drawing tool.
        return self.editor.selected_record()

    def test_insert_projection_undo_redo_and_delete_minimum(self):
        old=self.polygon()
        self.assertTrue(self.editor.insert_vertex([60,22]))
        new=self.editor.selected_record()
        self.assertEqual(new.geometry['points'][1],[60,20])
        self.assertEqual(new.derived_from,old.annotation_id)
        self.editor.undo_stack.undo()
        self.assertEqual(self.editor.document.active_annotation_ids,{old.annotation_id})
        self.editor.undo_stack.redo(); self.editor.select(new.annotation_id)
        self.editor.selected_vertex=1
        self.assertTrue(self.editor.delete_vertex())
        deleted=self.editor.selected_record()
        self.assertEqual(deleted.geometry,old.geometry)
        self.editor.undo_stack.undo()
        self.assertEqual(self.editor.document.active_annotation_ids,{new.annotation_id})
        self.editor.undo_stack.redo(); self.editor.select(deleted.annotation_id)
        self.editor.selected_vertex=0; self.editor.delete_vertex()
        self.editor.selected_vertex=0
        self.assertFalse(self.editor.delete_vertex())
        self.assertEqual(len(self.editor.selected_record().geometry['points']),3)
        self.assertIn('3',self.window.statusBar().currentMessage())

    def test_double_click_zoom_pan_modes_and_vertex_highlight(self):
        self.polygon()
        self.canvas.zoom(2)
        self.canvas.horizontalScrollBar().setValue(5)
        self.canvas.verticalScrollBar().setValue(5)
        self.click(60,18)  # real double-click sequence first presses just outside the edge
        QTest.mouseDClick(self.canvas.viewport(),Qt.MouseButton.LeftButton,pos=self.canvas.mapFromScene(QPointF(60,18)))
        self.assertEqual(self.editor.selected_record().geometry['points'][1],[60,20])
        self.assertEqual(self.editor.selected_vertex,1)
        self.assertEqual(self.editor.handles[1][2].brush().color().name(),'#ff5500')
        self.drag((60,20),(65,25))
        geometry=self.editor.selected_record().geometry
        for mode in ('raw','manual','auto_percentile','photometric_ref90'):
            from droplet_vision.display import DisplaySettings
            self.window.display_panel.set_settings(DisplaySettings(mode=mode))
            self.assertEqual(self.editor.selected_record().geometry,geometry)
        self.assertEqual(geometry['points'][1],[65,25])
        QTest.keyClick(self.canvas,Qt.Key.Key_Delete)
        self.assertEqual(len(self.editor.document.active_records()[0].geometry['points']),4)


@unittest.skipUnless(QT_AVAILABLE,'Qt unavailable')
class WandUiTests(unittest.TestCase):
    setUpClass=classmethod(tools_fixture.AnnotationToolsTests.setUpClass.__func__)
    setUp=tools_fixture.AnnotationToolsTests.setUp
    close_window=tools_fixture.AnnotationToolsTests.close_window
    click=tools_fixture.AnnotationToolsTests.click

    def image(self):
        raw=np.full((256,256),20,np.uint8)
        raw[30:60,30:60]=100; raw[90:120,90:120]=150
        self.window.raw_image=raw
        self.window.refresh_display()
        self.editor.update_tools()
        return raw

    def test_raw_preview_tolerance_cancel_confirm_compound_undo_and_correction(self):
        raw=self.image(); before=raw.copy()
        self.window.controller.cache.put(0,raw)
        with patch.object(self.window.controller,'request_frame') as reads:
            self.editor.actions['magic_wand'].trigger()
            tool=self.editor.tool
            self.click(40,40)
            self.assertTrue(self.editor.preview)
            self.assertFalse(self.editor.document.active_records())
            self.editor.wand_panel.tolerance.setValue(5)
            self.assertEqual(tool.operations[-1]['seed_reference'],100)
            self.editor.wand_panel.mode.setCurrentIndex(1)
            self.click(100,100)
            self.assertEqual(tool.mask.sum(),1800)
            self.editor.wand_panel.confirm_button.click()
            reads.assert_not_called()
        records=self.editor.document.active_records()
        self.assertEqual(len(records),2)
        for r in records:
            self.assertEqual(r.source,'manual'); self.assertEqual(r.review_status,'unreviewed')
            self.assertEqual(r.attributes['creation_tool'],'magic_wand')
            self.assertEqual(len(r.attributes['magic_wand_operations']),2)
            self.assertNotIn('mask',r.geometry)
        np.testing.assert_array_equal(raw,before)
        np.testing.assert_array_equal(self.window.controller.cache.get(0),before)
        self.editor.undo_stack.undo(); self.assertFalse(self.editor.document.active_records())
        self.editor.undo_stack.redo(); self.assertEqual(len(self.editor.document.active_records()),2)
        self.editor.select(records[0].annotation_id)
        a,b=records[0].geometry['points'][:2]
        self.assertTrue(self.editor.insert_vertex([(a[0]+b[0])/2,(a[1]+b[1])/2]))
        self.editor.switch_tool('magic_wand'); self.click(40,40)
        self.editor.wand_panel.cancel_button.click()
        self.assertFalse(self.editor.preview); self.assertIsNone(self.editor.tool.mask)

    def test_subtract_invalid_large_selection_and_dtype(self):
        raw=self.image()
        self.editor.switch_tool('magic_wand'); self.click(40,40)
        tool=self.editor.tool
        self.editor.wand_panel.mode.setCurrentIndex(2)
        self.click(40,40); self.assertEqual(tool.mask.sum(),0)
        self.editor.wand_panel.mode.setCurrentIndex(0)
        self.click(200,200)
        self.assertFalse(tool.valid)
        self.assertFalse(self.editor.wand_panel.confirm_button.isEnabled())
        self.assertIn('too large',self.window.statusBar().currentMessage())
        self.assertFalse(self.editor.document.active_records())
        self.window.raw_image=raw.astype(np.uint16); self.editor.update_tools()
        self.assertFalse(self.editor.actions['magic_wand'].isEnabled())


@unittest.skipUnless(QT_AVAILABLE,'Qt unavailable')
class LocalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])

    def test_default_chinese_persisted_english_and_stable_label_ids(self):
        with tempfile.TemporaryDirectory() as folder:
            store=QSettings(str(Path(folder)/'prefs.ini'),QSettings.Format.IniFormat)
            self.assertEqual(i18n.preferred_language(store),'zh_CN')
            with patch.dict(os.environ,{'DROPLET_VISION_LANGUAGE':''}),patch.object(i18n,'preferences',return_value=store):
                window=MainWindow()
                self.assertIn('文件',[a.text() for a in window.menuBar().actions()])
                label=window.annotation_panel.labels.item(0)
                stable=label.data(Qt.ItemDataRole.UserRole)
                self.assertEqual(label.text(),'父液滴')
                with patch.object(QMessageBox,'information') as notice:
                    window.change_language('en_US'); notice.assert_not_called()
                self.assertIn('File',[a.text() for a in window.menuBar().actions()])
                self.assertEqual(window.annotation_panel.labels.item(0).data(Qt.ItemDataRole.UserRole),stable)
                window.close()
                self.assertEqual(i18n.preferred_language(QSettings(str(Path(folder)/'prefs.ini'),QSettings.Format.IniFormat)),'en_US')
                window=MainWindow()
                self.assertIn('File',[a.text() for a in window.menuBar().actions()])
                self.assertEqual(window.annotation_panel.labels.item(0).data(Qt.ItemDataRole.UserRole),stable)
                self.assertEqual(window.annotation_panel.labels.item(0).text(),'Parent droplet')
                window.close()
        i18n.set_language('en_US')


    def test_missing_keys_and_stable_ids(self):
        i18n.set_language('zh_CN')
        self.assertEqual(i18n.tr('experimental_feature_x'),'experimental_feature_x')
        self.assertEqual(i18n.tr('parent_droplet'),'parent_droplet')
        self.assertEqual(i18n.tr('unknown_new_key'),'unknown_new_key')
        with patch.dict(i18n._catalogs['zh_CN'],clear=True):
            self.assertEqual(i18n.tr('File'),'File')
        from PySide6.QtCore import QCoreApplication
        self.assertEqual(QCoreApplication.translate('QFileDialog', 'File name:'), 'File name:')
        i18n.set_language('en_US')


@unittest.skipUnless(QT_AVAILABLE and os.environ.get('DROPLET_VISION_TEST_CINE'), 'Real Cine/Qt not enabled')
class RealAnnotationUxTests(unittest.TestCase):
    def test_wand_correction_display_modes_and_reopened_document(self):
        from copy import deepcopy
        from droplet_vision.display import DisplaySettings
        from droplet_vision.annotations.magic_wand import mask_to_polygons
        from PIL import Image
        app=QApplication.instance() or QApplication([])
        source=Path(os.environ['DROPLET_VISION_TEST_CINE'])
        before=source.stat()
        window=MainWindow(Path(__file__).parent/'fixtures/experimental_taxonomy.json')
        try:
            window.open_cine(source)
            wait_for(lambda: window.current_record is not None)
            index=min(16739,window.metadata.frame_count-1)
            window.navigate(index)
            wait_for(lambda: window.current_record.frame_index==index)
            window.annotation_panel.labels.setCurrentRow(0)
            editor=window.editor
            raw=window.raw_image.copy()
            editor.switch_tool('magic_wand')
            editor.wand_panel.tolerance.setValue(1)
            # A test seed only; no physical interpretation or automatic label.
            editor.tool.mouse_press([min(100,raw.shape[1]-1),min(110,raw.shape[0]-1)])
            self.assertTrue(editor.tool.valid)
            self.assertTrue(mask_to_polygons(editor.tool.mask))
            self.assertTrue(editor.tool.commit())
            original=editor.document.active_records()[0]
            editor.select(original.annotation_id)
            a,b=original.geometry['points'][:2]
            self.assertTrue(editor.insert_vertex([(a[0]+b[0])/2,(a[1]+b[1])/2]))
            inserted=editor.selected_record()
            self.assertEqual(inserted.derived_from,original.annotation_id)
            self.assertTrue(editor.delete_vertex())
            editor.undo_stack.undo(); editor.undo_stack.redo()
            current=editor.document.active_records()[0]
            editor.select(current.annotation_id)
            moved=deepcopy(current.geometry)
            moved['points'][0][0]=max(0,moved['points'][0][0]-.25)
            self.assertTrue(editor.edit_annotation(current.annotation_id,moved))
            expected=[r.to_dict() for r in editor.document.active_records()]
            for mode in ('raw','photometric_ref90','manual','auto_percentile'):
                window.display_panel.set_settings(DisplaySettings(mode=mode))
                np.testing.assert_array_equal(window.raw_image,raw)
                np.testing.assert_array_equal(window.controller.cache.get(index),raw)
                self.assertEqual([r.to_dict() for r in editor.document.active_records()],expected)
            with tempfile.TemporaryDirectory() as folder:
                output=Path(folder)/'wand.annotations.json'
                editor.save(output)
                window.export_frame(Path(folder)/'raw.png')
                with Image.open(Path(folder)/'raw.png') as png:
                    np.testing.assert_array_equal(np.asarray(png),raw)
                window.close()
                window=MainWindow(Path(__file__).parent/'fixtures/experimental_taxonomy.json')
                window.open_cine(source)
                wait_for(lambda: window.current_record is not None)
                self.assertTrue(window.editor.load(output))
                self.assertEqual([r.to_dict() for r in window.editor.document.active_records()],expected)
        finally:
            with patch.object(QMessageBox,'warning',return_value=QMessageBox.StandardButton.Discard):
                window.close()
        after=source.stat()
        self.assertEqual((before.st_size,before.st_mtime_ns),(after.st_size,after.st_mtime_ns))

