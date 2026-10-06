"""Marker hit testing uses native slider geometry without taking over dragging."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from test_ui_main_window import QT_AVAILABLE, wait_for
import test_ui_annotation_tools as tools_tests

if QT_AVAILABLE:
    from PySide6.QtCore import Qt, QPoint, QEvent, QSettings
    from PySide6.QtGui import QHelpEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionSlider
    from droplet_vision.ui.widgets.timeline import Timeline
    from droplet_vision.ui import i18n
    from droplet_vision.annotations import AnnotationRecord
    from droplet_vision.annotations.frame_state import FrameStateRecord


@unittest.skipUnless(QT_AVAILABLE, 'Qt unavailable')
class MarkerInteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.timeline = Timeline()
        self.timeline.resize(700,55)
        self.timeline.set_count(1001)
        self.timeline.show()
        self.addCleanup(self.timeline.close)
        QTest.qWait(20)
        self.slider = self.timeline.slider
        self.requests = []
        self.timeline.requested.connect(self.requests.append)

    def x(self, frame):
        return next(iter(self.slider.marker_positions({frame})))

    def test_click_endpoints_middle_expanded_hit_and_debounce(self):
        self.slider.set_markers({0,500,1000})
        for frame,offset in ((0,6),(500,6),(1000,-6)):
            self.slider.setValue(200)  # Pending native debounce must not emit an extra seek.
            self.requests.clear()
            QTest.mouseClick(self.slider,Qt.MouseButton.LeftButton,pos=QPoint(self.x(frame)+offset,4))
            QTest.qWait(70)
            self.assertEqual(self.requests,[frame])
            self.assertEqual(self.timeline.spinbox.value(),frame)

    def test_dense_column_chooses_nearest_current_frame(self):
        self.timeline.set_count(100001)
        self.slider.set_markers(range(49000,51001))
        self.timeline.set_frame(50001)
        columns = self.slider.marker_columns()
        self.assertLess(len(columns),len(self.slider.marked_frames))
        x=self.x(50001);frames=columns[x]
        self.assertGreater(len(frames),1)
        QTest.mouseClick(self.slider,Qt.MouseButton.LeftButton,pos=QPoint(x,4))
        self.assertEqual(self.requests,[50001])

    def test_outside_hit_native_click_drag_and_keyboard(self):
        self.slider.set_markers({500})
        self.timeline.set_frame(100)
        option=QStyleOptionSlider();self.slider.initStyleOption(option)
        handle=self.slider.style().subControlRect(QStyle.ComplexControl.CC_Slider,option,QStyle.SubControl.SC_SliderHandle,self.slider)
        start=handle.center();end=QPoint(self.x(750),start.y())
        self.assertIsNone(self.slider.marker_at(end))
        QTest.mousePress(self.slider,Qt.MouseButton.LeftButton,pos=start)
        self.assertTrue(self.slider.isSliderDown())
        QTest.mouseMove(self.slider,end)
        QTest.mouseRelease(self.slider,Qt.MouseButton.LeftButton,pos=end)
        self.assertGreater(self.slider.value(),600)
        self.assertFalse(self.slider.isSliderDown())
        previous=self.slider.value()
        QTest.keyClick(self.slider,Qt.Key.Key_Right)
        self.assertEqual(self.slider.value(),previous+1)
        QTest.mouseClick(self.slider,Qt.MouseButton.LeftButton,pos=QPoint(self.x(100),start.y()))
        self.assertLess(self.slider.value(),previous)

    def test_tooltip_event_lazy_details_and_language(self):
        self.slider.set_markers({500})
        self.slider.marker_details=lambda frame:[i18n.tr('Objects: {count}').format(count=3)]
        with tempfile.TemporaryDirectory() as folder, patch.object(i18n,'preferences',return_value=QSettings(str(Path(folder)/'prefs.ini'),QSettings.Format.IniFormat)):
            previous=i18n.current_language()
            try:
                for language,label in [('en_US','Objects: 3'),('zh_CN','对象：3')]:
                    i18n.set_language(language)
                    pos=QPoint(self.x(500),4)
                    event=QHelpEvent(QEvent.Type.ToolTip,pos,self.slider.mapToGlobal(pos))
                    with patch('droplet_vision.ui.widgets.annotation_markers.QToolTip.showText') as show:
                        self.app.sendEvent(self.slider,event)
                        self.assertIn(label,show.call_args.args[1])
                        self.assertIn('500',show.call_args.args[1])
            finally:
                i18n.set_language(previous)


@unittest.skipUnless(QT_AVAILABLE, 'Qt unavailable')
class MarkerDocumentTests(unittest.TestCase):
    setUpClass = tools_tests.AnnotationToolsTests.__dict__['setUpClass']
    setUp = tools_tests.AnnotationToolsTests.setUp
    close_window = tools_tests.AnnotationToolsTests.close_window

    def test_human_state_prediction_history_reload_and_navigation(self):
        doc=self.editor.document
        model=AnnotationRecord('fake',5,'experimental_feature_x','point',{'point':[8,8]},source='model')
        doc.add_record(model,'prediction')
        state=FrameStateRecord('fake',50,state_ids=('nucleation','bubble_growth'),source='model',review_status='accepted')
        doc.add_frame_state(state);doc.activate_frame_state(50,state.record_id)
        self.editor.changed()
        slider=self.window.timeline.slider
        self.assertEqual(slider.marked_frames,{50})
        self.assertIn('Nucleation',' '.join(self.editor.marker_details(50)))
        x=next(iter(slider.marker_positions({50})))
        QTest.mouseClick(slider,Qt.MouseButton.LeftButton,pos=QPoint(x,4))
        wait_for(lambda:self.window.current_record.frame_index==50)
        self.assertTrue(self.editor.create_annotation('point',{'point':[50,50]}))
        aid=doc.active_records(50)[0].annotation_id
        self.editor.select(aid);self.editor.deactivate_selected()
        self.editor.undo()
        self.assertIn(aid,doc.active_annotation_ids)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'annotations.json';self.editor.save(path);self.editor.load(path)
        self.assertEqual(slider.marked_frames,{50})

