import os
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import numpy as np
import test_ui_annotation_tools as tool_tests
from test_ui_main_window import QT_AVAILABLE, wait_for

if QT_AVAILABLE:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QApplication, QCheckBox, QHBoxLayout, QMessageBox, QStyle, QStyleOptionSlider
    from PySide6.QtTest import QTest
    from droplet_vision.ui import i18n
    from droplet_vision.annotations import AnnotationRecord
    from droplet_vision.annotations.scheme import load_scheme
    from droplet_vision.ui.widgets.annotation_markers import human_frames


@unittest.skipUnless(QT_AVAILABLE,'Qt unavailable')
class WorkspaceTests(unittest.TestCase):
    setUpClass = tool_tests.AnnotationToolsTests.__dict__['setUpClass']
    close_window = tool_tests.AnnotationToolsTests.close_window

    def setUp(self):
        tool_tests.AnnotationToolsTests.setUp(self)
        self.workflow=self.editor.workflow
        self.workflow.apply_scheme()

    def record(self,label='parent_droplet',name=''):
        self.window.annotation_panel.select_label_id(label)
        self.workflow.instance_name.setText(name)
        self.assertTrue(self.editor.create_annotation('polygon',{'points':[[20,20],[80,20],[50,70]]}))
        return self.editor.document.active_records()[-1]

    def test_left_scroll_wrapping_and_sections(self):
        left=self.window.info_dock
        self.assertTrue(left.isAncestorOf(self.workflow.scheme_group))
        self.assertTrue(left.isAncestorOf(self.window.annotation_panel.records_group))
        self.assertFalse(self.window.annotation_dock.isAncestorOf(self.workflow.scheme_group))
        panel=self.window.annotation_data_panel
        path=Path(tempfile.gettempdir())/('a'*130)/('b'*110+'.annotations.json')
        panel.update_document(self.editor.document,path,None)
        self.window.resizeDocks([left],[290],Qt.Orientation.Horizontal)
        QTest.qWait(80)
        self.assertEqual(panel.location.text(),str(path.resolve()))
        self.assertTrue(panel.location.wordWrap())
        self.assertTrue(panel.location.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse)
        self.assertGreater(panel.location.heightForWidth(240),panel.location.fontMetrics().height())
        self.assertTrue(panel.location.sizePolicy().hasHeightForWidth())
        self.assertGreaterEqual(panel.location.height(),panel.location.heightForWidth(panel.location.width()))
        scroll=left.widget();self.assertTrue(scroll.widgetResizable())
        self.assertGreater(scroll.verticalScrollBar().maximum(),0)
        for button in (panel.copy_button,panel.folder_button):
            scroll.ensureWidgetVisible(button);QTest.qWait(10)
            self.assertGreaterEqual(button.width(),button.minimumSizeHint().width())
        self.assertTrue(all(v.wordWrap() for v in self.window.metadata_panel.values.values()))

    def test_object_buttons_order_exclusive_dynamic_and_tools(self):
        panel=self.window.annotation_panel
        expected=['parent_droplet','internal_cavity_candidate','daughter_droplet','flame','support_structure','soot']
        self.assertEqual(list(panel.object_buttons),expected)
        panel.object_buttons['parent_droplet'].click()
        self.assertEqual(self.editor.tool_key,'polygon')
        panel.object_buttons['daughter_droplet'].click()
        self.assertEqual(sum(b.isChecked() for b in panel.object_buttons.values()),1)
        layout=self.editor.tool_group.layout();self.assertIsInstance(layout,QHBoxLayout)
        self.assertEqual(layout.count(),4);self.assertNotIn('bbox',self.editor.tool_buttons)
        custom=deepcopy(self.workflow.scheme);custom.update(scheme_id='custom',status='custom')
        custom['display']['object_order']=list(reversed(expected))
        custom['objects']['labels'].append({'label_id':'experimental_feature_x','display_name':'Novel X',
            'allowed_geometry_types':['point'],'enabled':True,'group':None,'attributes':{}})
        self.workflow.scheme_selector.addItem('custom',custom)
        self.workflow.scheme_selector.setCurrentIndex(self.workflow.scheme_selector.count()-1)
        self.workflow.apply_scheme()
        self.assertEqual(list(panel.object_buttons)[:6],list(reversed(expected)))
        panel.object_buttons['experimental_feature_x'].click()
        self.assertEqual(self.editor.tool_key,'point')

    def test_overlay_list_palette_reload_geometry_and_selection(self):
        a=self.record(name='Parent_01');b=self.record('daughter_droplet','Daughter_01')
        c=self.record('daughter_droplet','Daughter_02')
        colors={a.annotation_id:'#3B6FB6',b.annotation_id:'#2A9D8F',c.annotation_id:'#E9A23B'}
        self.editor.changed()
        for aid,color in colors.items():
            item=self.canvas.overlays.by_id[aid]
            self.assertEqual(item.data(1),color)
            self.editor.select(aid)
            self.assertEqual(item.pen().color().name().upper(),color)
            li=next(self.window.annotation_panel.items.item(i) for i in range(3)
                    if self.window.annotation_panel.items.item(i).data(Qt.ItemDataRole.UserRole)==aid)
            self.assertEqual(li.data(Qt.ItemDataRole.UserRole+1),color)
        before=[r.to_dict() for r in self.editor.document.active_records()]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'test.json';self.editor.save(path);self.editor.load(path)
        self.assertEqual(before,[r.to_dict() for r in self.editor.document.active_records()])
        custom=deepcopy(self.workflow.scheme);custom.update(scheme_id='custom',status='custom')
        custom['display']['object_styles']['parent_droplet']['color']='#123456'
        self.workflow.scheme_selector.addItem('new palette',custom)
        self.workflow.scheme_selector.setCurrentIndex(self.workflow.scheme_selector.count()-1)
        self.workflow.apply_scheme()
        self.assertEqual(self.canvas.overlays.by_id[a.annotation_id].data(1),'#123456')
        self.assertEqual(before,[r.to_dict() for r in self.editor.document.active_records()])

    def test_markers_human_state_prediction_deactivate_undo_save_load(self):
        model=AnnotationRecord('fake',5,'parent_droplet','point',{'point':[5,5]},source='model')
        self.editor.document.add_record(model,layer_id='prediction');self.editor.changed()
        self.assertNotIn(5,self.window.timeline.slider.marked_frames)
        r=self.record();self.assertIn(0,self.window.timeline.slider.marked_frames)
        self.editor.select(r.annotation_id);self.editor.deactivate_selected()
        self.assertNotIn(0,self.window.timeline.slider.marked_frames)
        self.editor.undo_stack.undo();self.assertIn(0,self.window.timeline.slider.marked_frames)
        self.window.navigate(10);wait_for(lambda:self.window.current_record.frame_index==10)
        self.workflow.checkboxes['nucleation'].trigger()
        self.assertIn(10,self.window.timeline.slider.marked_frames)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'markers.json';self.editor.save(path);self.editor.load(path)
        self.assertEqual(self.window.timeline.slider.marked_frames,{0,10})

    def test_marker_style_mapping_dense_and_slider_inputs(self):
        slider=self.window.timeline.slider;slider.resize(500,32);slider.setRange(0,10000)
        slider.set_markers({0,5000,10000})
        positions=sorted(slider.marker_positions());self.assertEqual(len(positions),3)
        option=QStyleOptionSlider();slider.initStyleOption(option)
        handle=slider.style().subControlRect(QStyle.ComplexControl.CC_Slider,option,QStyle.SubControl.SC_SliderHandle,slider)
        self.assertAlmostEqual(positions[0],handle.width()//2,delta=2)
        self.assertAlmostEqual(positions[1],slider.width()/2,delta=2)
        self.assertLess(positions[-1],slider.width())
        slider.set_markers(set(range(10001)))
        self.assertLessEqual(len(slider.marker_positions()),slider.width())
        slider.setValue(400);before=slider.value();slider.grab()
        self.assertEqual(slider.value(),before)

    def test_common_more_multi_exclusivity_and_final_names(self):
        self.assertEqual(sum(isinstance(v,QCheckBox) for v in self.workflow.checkboxes.values()),4)
        self.assertEqual(len(self.workflow.more_actions),6)
        self.assertTrue(all(a.isCheckable() for a in self.workflow.more_actions.values()))
        self.workflow.more_actions['nucleation'].trigger();self.workflow.more_actions['puffing'].trigger()
        self.assertIn('(2)',self.workflow.more_button.text())
        self.assertEqual(set(self.editor.document.frame_state(0).state_ids),{'nucleation','puffing'})
        self.workflow.checkboxes['simple_evaporation'].click()
        self.assertFalse(any(a.isChecked() for a in self.workflow.more_actions.values()))
        self.workflow.more_actions['puffing'].trigger()
        self.assertFalse(self.workflow.checkboxes['simple_evaporation'].isChecked())
        try:
            i18n.set_language('zh_CN');self.workflow._build_states()
            self.assertEqual(self.workflow.more_actions['nucleation'].text(),'成核（Nucleation）')
            self.assertEqual(self.workflow.more_actions['puffing'].text(),'喷发（Puffing）')
            i18n.set_language('en_US');self.workflow._build_states()
            self.assertEqual(self.workflow.more_actions['nucleation'].text(),'Nucleation')
        finally:i18n.set_language('en_US')

    def test_notes_conditional_keep_cancel_clear_and_roundtrip(self):
        w=self.workflow
        self.assertTrue(w.notes.isHidden())
        w.uncertain.click();self.assertFalse(w.notes.isHidden())
        w.uncertain.click();self.assertTrue(w.notes.isHidden())
        w.has_note.click();self.assertFalse(w.notes.isHidden())
        w.notes.setPlainText('Review edge');w.apply_notes.click()
        with patch.object(QMessageBox,'exec'),patch.object(QMessageBox,'clickedButton',return_value=None):
            w.has_note.click()
        self.assertEqual(w.notes.toPlainText(),'Review edge');self.assertTrue(w.has_note.isChecked())
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'notes.json';self.editor.save(path);self.editor.load(path)
            value=json.loads(path.read_text(encoding='utf-8'))
            self.assertNotIn('has_note',json.dumps(value))
        self.assertTrue(w.has_note.isChecked());self.assertFalse(w.notes.isHidden())
        def choose_clear(box):
            for b in box.buttons():
                if box.buttonRole(b)==QMessageBox.ButtonRole.DestructiveRole:return b
        with patch.object(QMessageBox,'exec'),patch.object(QMessageBox,'clickedButton',choose_clear):
            w.has_note.click()
        self.assertEqual(w.notes.toPlainText(),'');self.assertTrue(w.notes.isHidden())

    def test_invalid_display_shows_warning_without_changing_records(self):
        custom=deepcopy(self.workflow.scheme);custom.update(scheme_id='bad_style',status='custom')
        custom['display']['palette']=['bad']
        self.workflow.scheme_selector.addItem('bad',custom)
        self.workflow.scheme_selector.setCurrentIndex(self.workflow.scheme_selector.count()-1)
        with self.assertLogs('droplet_vision.annotations.display_style',level='WARNING'):
            self.workflow.apply_scheme()
        self.assertIn('safe defaults',self.workflow.active_label.text())
        self.assertEqual(self.window.annotation_panel.display_config['palette'],['#808080'])

    def test_modify_dialog_state_name_updates_runtime_display(self):
        from droplet_vision.ui.panels.workflow_panel import CustomSchemeDialog
        dialog=CustomSchemeDialog(self.workflow.scheme,self.window)
        try:
            index=next(i for i,(kind,row) in enumerate(dialog.rows)
                       if kind=='state' and row['state_id']=='nucleation')
            dialog.table.item(index,1).setText('Custom state display')
            custom=dialog.custom_value()
            self.assertEqual(custom['display']['state_names']['nucleation'][i18n.current_language()],
                             'Custom state display')
            self.assertEqual(self.workflow.scheme['scheme_id'],'droplet_annotation_scheme_v1')
        finally:dialog.close()
