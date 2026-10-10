"""Cine Viewer v1 shell for the future Droplet Annotation Workstation."""
from __future__ import annotations
from pathlib import Path
from dataclasses import replace
from bisect import bisect_right
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout,
                               QFileDialog, QMessageBox, QLabel, QListWidget, QInputDialog, QDockWidget, QScrollArea, QGroupBox, QToolButton)
from ..annotations import AnnotationLayer, Bookmark, ViewerSession
from ..annotations.taxonomy import load_taxonomy, default_taxonomy_path
from ..annotations.display_style import record_colors
from ..display import DisplaySettings, render_display
from ..display.photometric import MODE, PRESET_ID, REFERENCE_FRACTION
from .cine_controller import CineController
from .display import export_png
from .widgets.image_canvas import ImageCanvas
from .widgets.timeline import Timeline
from .widgets.transport_controls import TransportControls, REVIEW_PLAYBACK_FPS
from .review_playback import ReviewPlayback
from .panels.metadata_panel import MetadataPanel
from .panels.annotation_data_panel import AnnotationDataPanel
from .panels.annotation_panel import AnnotationPanel
from .panels.layer_panel import LayerPanel
from .panels.display_panel import DisplayPanel
from .annotation_editor import AnnotationEditor
from .annotation_queue import QueueCoordinator
from .i18n import tr, initialize, save_language, current_language, set_language, retranslate_tree
from .branding import app_icon, AboutDialog


class MainWindow(QMainWindow):
    cine_open_requested = Signal(object)

    def __init__(self, taxonomy_path=None, parent=None, controller=None):
        super().__init__(parent)
        initialize()
        self.setWindowIcon(app_icon())
        self.about_dialog = None
        self.setWindowTitle(tr("Droplet Annotation Workstation"))
        self.resize(1280, 850)
        self.controller = controller or CineController(self)
        self.metadata = None
        self.current_record = None
        self.raw_image = None
        self.cine_path = None
        self.session = None
        self._pending_session = None
        self.layers = [AnnotationLayer("manual", "Manual", "manual"),
                       AnnotationLayer("prediction", "Prediction", "prediction", locked=True),
                       AnnotationLayer("reviewed", "Reviewed", "reviewed"),
                       AnnotationLayer("ground_truth", "Ground truth", "ground_truth", locked=True)]
        labels = load_taxonomy(taxonomy_path or default_taxonomy_path())
        central = QWidget()
        layout = QVBoxLayout(central)
        self.metadata_panel = MetadataPanel()
        self.canvas = ImageCanvas()
        layout.addWidget(self.canvas, 1)
        self.display_panel = DisplayPanel()
        self.display_panel.auto_fit.toggled.connect(self.canvas.set_auto_fit)
        self.canvas.auto_fit_changed.connect(self.display_panel.auto_fit.setChecked)
        self.canvas.fitted.connect(lambda: self.statusBar().showMessage(tr('Fitted to view; resizing will fit automatically.')))
        left = QWidget()
        left_layout = self.left_layout = QVBoxLayout(left)
        left_layout.addWidget(self.metadata_panel)
        self.annotation_data_panel = AnnotationDataPanel()
        display_group = QGroupBox(tr('Display'))
        QVBoxLayout(display_group).addWidget(self.display_panel)
        left_layout.addWidget(display_group)
        left_layout.addWidget(self.annotation_data_panel)
        left_layout.addStretch()
        self.info_dock = self._scroll_dock(tr('Image and display'), 'imageInfoDock', left,
                                           Qt.DockWidgetArea.LeftDockWidgetArea)
        self.annotation_panel = AnnotationPanel(labels)
        self.layer_panel = LayerPanel(self.layers)
        self.layer_panel.changed.connect(self.refresh_overlays)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.annotation_panel)
        right_layout.addWidget(self.layer_panel)
        right_layout.addStretch()
        self.annotation_dock = self._scroll_dock(tr('Annotation workspace'), 'annotationWorkspaceDock', right,
                                                 Qt.DockWidgetArea.RightDockWidgetArea)
        self.bookmarks_list = QListWidget()
        self.bookmarks_list.itemDoubleClicked.connect(lambda item: self.navigate(item.data(Qt.ItemDataRole.UserRole)))
        self.bookmarks_dock = QDockWidget(tr('Bookmarks (double-click to navigate)'), self)
        self.bookmarks_dock.setObjectName('bookmarksDock')
        self.bookmarks_dock.setWidget(self.bookmarks_list)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.bookmarks_dock)
        self.bookmarks_dock.hide()
        self.timeline = Timeline()
        self.timeline.requested.connect(self.navigate)
        self.timeline.slider.sliderPressed.connect(self.pause)
        self.transport = TransportControls()
        self.transport.step.connect(self.step)
        self.transport.first.connect(lambda: self.navigate(0))
        self.transport.last.connect(lambda: self.navigate(self.controller.state.frame_count - 1))
        self.transport.toggle_play.connect(self.toggle_play)
        self.transport.fps_changed.connect(self.set_playback_fps)
        self.time_label = QLabel(tr("Relative timestamp: unknown"))
        layout.addWidget(self.timeline)
        layout.addWidget(self.transport)
        layout.addWidget(self.time_label)
        self.setCentralWidget(central)
        self.display_label = QLabel(tr("Display: RAW"))
        self.statusBar().addPermanentWidget(self.display_label)
        self.display_panel.changed.connect(self.refresh_display)
        self.display_panel.recalculate_requested.connect(self.controller.recalculate_reference)
        self.playback = QTimer(self)
        self.review_clock = ReviewPlayback()
        self._review_desired = None
        self.playback.setInterval(100)
        self.playback.timeout.connect(self._tick)
        self.controller.opened.connect(self._opened)
        self.controller.frame_ready.connect(self._frame_ready)
        self.controller.failed.connect(self._error)
        self.controller.photometric_changed.connect(self._photometric_changed)
        self._menus()
        self.editor = AnnotationEditor(self, taxonomy_path or default_taxonomy_path())
        self.left_layout.insertWidget(self.left_layout.count()-1, self.annotation_panel.records_group)
        self.queue_manager = QueueCoordinator(self)
        from .review_package import ReviewCoordinator
        self.review_manager = ReviewCoordinator(self)
        self.reorder_menus()
        self.transport.setEnabled(False)
        self.statusBar().showMessage(tr("Open a Cine to begin. Display pixels are separate from scientific raw values."))

    def _scroll_dock(self, title, name, content, area):
        dock = QDockWidget(title, self)
        dock.setObjectName(name)
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(290)
        scroll.setWidget(content)
        dock.setWidget(scroll)
        self.addDockWidget(area, dock)
        return dock

    def _action(self, menu, text, callback, shortcut=None):
        action = QAction(tr(text), self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(callback)
        menu.addAction(action)
        return action

    def _menus(self):
        self.language_toggle = QToolButton(self)
        self.language_toggle.setMinimumWidth(self.language_toggle.fontMetrics().horizontalAdvance('English') + 20)
        self.language_toggle.setText('English' if current_language() == 'zh_CN' else '中文')
        self.language_toggle.setToolTip(tr('Switch language'))
        self.language_toggle.clicked.connect(lambda: self.change_language(
            'en_US' if current_language() == 'zh_CN' else 'zh_CN'))
        self.menuBar().setCornerWidget(self.language_toggle)
        settings = self.menuBar().addMenu(tr('Settings'))
        language = settings.addMenu(tr('Language'))
        self.language_actions = {}
        for code, title in [('zh_CN', '中文'), ('en_US', 'English')]:
            action = language.addAction(title)
            action.setCheckable(True)
            action.setChecked(code == current_language())
            self.language_actions[code] = action
            action.triggered.connect(lambda checked=False, value=code: self.change_language(value))
        file_menu = self.menuBar().addMenu(tr("File"))
        self.file_menu = file_menu
        self._action(file_menu, tr("Open Cine..."), self.open_dialog, "Ctrl+O")
        self._action(file_menu, tr("Close Cine"), self.close_cine)
        self.export_action = self._action(file_menu, tr("Export Current Frame..."), self.export_dialog, "Ctrl+E")
        self.export_action.setToolTip(tr("Export Current Frame exports raw scientific pixels, not display-enhanced preview."))
        self.export_action.setStatusTip(self.export_action.toolTip())
        self._action(file_menu, tr("Save Session As..."), self.save_session_dialog, "Ctrl+S")
        self._action(file_menu, tr("Load Session..."), self.load_session_dialog, "Ctrl+L")
        self._action(file_menu, tr("Exit"), self.close, "Ctrl+Q")
        view = self.menuBar().addMenu(tr("View"))
        for dock in (self.info_dock, self.annotation_dock, self.bookmarks_dock):
            view.addAction(dock.toggleViewAction())
        self._action(view, tr("Raw display"), self.display_panel.show_raw, "R")
        self._action(view, tr("Photometric Ref90 v1"), self.display_panel.show_photometric, "P")
        self._action(view, tr("Enhanced display (previous mode)"), self.display_panel.show_enhanced, "E")
        self._action(view, tr("Reset Display"), self.display_panel.reset)
        self._action(view, tr("Fit image"), self.canvas.fit_image, "F")
        self._action(view, tr("Zoom in"), lambda: self.canvas.zoom(1.2), "+")
        self._action(view, tr("Zoom out"), lambda: self.canvas.zoom(1 / 1.2), "-")
        for shortcut, delta in [("Left", -1), ("Right", 1), ("Shift+Left", -10),
                                ("Shift+Right", 10), ("PgUp", -100), ("PgDown", 100),
                                ("Ctrl+PgUp", -1000), ("Ctrl+PgDown", 1000)]:
            self._action(view, shortcut, lambda checked=False, d=delta: self.step(d), shortcut)
        self._action(view, tr("First frame"), lambda: self.navigate(0), "Home")
        self._action(view, tr("Last frame"), lambda: self.navigate(self.controller.state.frame_count - 1), "End")
        self._action(view, tr("Review playback"), self.toggle_play)
        # Canvas owns Space; text editors and focused buttons retain native behavior.
        self.space_shortcut = QShortcut(QKeySequence("Space"), self.canvas)
        self.space_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.space_shortcut.setAutoRepeat(False)
        self.space_shortcut.activated.connect(self._canvas_space)
        annotation = self.menuBar().addMenu(tr("Annotation"))
        self.annotation_menu = annotation
        self._action(annotation, tr("Bookmark current frame"), self.add_bookmark, "B")
        self._action(annotation, tr("Bookmark with note/tags..."), self.bookmark_dialog)
        self._action(annotation, tr("Session notes..."), self.notes_dialog)
        model = self.menuBar().addMenu(tr("Model"))
        future = model.addAction(tr("Prediction providers — future extension"))
        future.setEnabled(False)
        help_menu = self.menuBar().addMenu(tr("Help"))
        self._action(help_menu, tr('About'), self.show_about)

    def _canvas_space(self):
        draft = getattr(self.editor.tool, 'draft', None)
        if draft is not None and draft.active:
            if draft.closed:
                # Same validation and compound undo path as the Confirm buttons.
                self.editor.tool.commit()
            else:
                self.editor.message(tr('Close the polygon before pressing Space to confirm.'))
            return
        self.toggle_play()

    def reorder_menus(self):
        actions = {a.text(): a for a in self.menuBar().actions()}
        for title in ('File', 'Annotation', 'Queue', 'View', 'Model', 'Settings', 'Functions', 'Help'):
            action = actions[tr(title)]
            self.menuBar().removeAction(action)
            self.menuBar().addAction(action)

    def show_about(self):
        if self.about_dialog is None:
            self.about_dialog = AboutDialog(self)
        self.about_dialog.retranslate()
        self.about_dialog.show()
        self.about_dialog.raise_()

    def open_dialog(self):
        filename, _ = QFileDialog.getOpenFileName(self, tr("Open Cine"), "", "Phantom Cine (*.cine)")
        if filename:
            self.open_cine(filename)

    def change_language(self, language):
        try:
            save_language(language)
            previous = current_language()
            set_language(language)
            retranslate_tree(self, previous)
            self.language_toggle.setText('English' if language == 'zh_CN' else '中文')
            for code, action in self.language_actions.items():
                action.setChecked(code == language)
            if self.session is not None:
                self.session.ui_state['language'] = language
            self.editor.workflow.retranslate()
            self.metadata_panel.retranslate()
            self.editor.tool_settings.show_tool(self.editor.tool_key)
            self.editor.tool_settings.refresh()
            self.editor.wand_panel.tolerance_label.setText(tr('Tolerance: ') + str(self.editor.wand_panel.tolerance.value()))
            self.editor.update_title()
            self.editor.update_counts()
            self.layer_panel.drawing_into.setText(tr('Drawing into: ') + self.layer_panel.active_layer.currentText())
            self.display_panel.set_settings(self.display_panel.settings, emit=False)
            self.display_panel.set_photometric(self.controller.photometric, self.controller.photometric_error,
                                                cine_open=self.metadata is not None)
            # Refresh list captions without rebuilding geometry/handles or drafts.
            if self.current_record is not None:
                records = [a for layer in self.layers for a in layer.annotations
                           if a.cine_id == self.current_record.cine_id and a.frame_index == self.current_record.frame_index]
                projections = list(self.editor.projections().values())
                suppressed = self.editor.document.support_suppressed_ids(self.current_record.frame_index) if self.editor.document else set()
                records = [r for r in records if r.annotation_id not in suppressed]
                records += projections
                self.annotation_panel.set_records(records, record_colors(self.annotation_panel.display_config, records),
                                                  self.editor.hidden_ids(), {r.annotation_id for r in projections})
                self.annotation_panel.select_record(self.editor.selected_record())
                record = self.current_record
                value = 'unknown' if record.timestamp_s is None else f'{record.timestamp_s:.9f} s'
                self.time_label.setText(tr(f'Frame: {record.frame_index} / {self.metadata.frame_count - 1}    Relative timestamp: {value}    {record.timing_status.value}'))
            for delta, button in self.transport.jump_buttons.items():
                button.setToolTip(tr('Jump {delta} frames').format(delta=f'{delta:+d}'))
            self.queue_manager.refresh()
            self.review_manager.refresh()
            if self.review_manager.batch_window is not None:
                self.review_manager.batch_window.retranslate()
            if self.about_dialog is not None:
                self.about_dialog.retranslate()
            self.display_label.setText(tr('Display: ') + self.display_panel.mode.currentText())
            self.statusBar().showMessage(tr('Language changed. Current editing state preserved.'))
        except OSError as error:
            self._error(str(error))

    def _reset(self):
        self.pause()
        self.editor.reset()
        self.timeline.set_count(0)
        self.transport.setEnabled(False)
        self.canvas.clear_image()
        self.raw_image = self.current_record = self.metadata = self.session = None
        self.display_panel.reset()
        self.display_panel.set_photometric()
        self.time_label.setText(tr("Relative timestamp: unknown"))
        self.metadata_panel.clear()
        self.bookmarks_list.clear()
        for layer in self.layers:
            layer.annotations.clear()
        self.annotation_panel.set_records([])

    def open_cine(self, path, session=None):
        if not self.editor.confirm_discard():
            return False
        self.review_manager.leave()
        self.cine_open_requested.emit(Path(path))
        self._reset()
        self.cine_path = Path(path)
        self._pending_session = session
        self.display_panel.show_photometric()
        self.display_panel.set_photometric(cine_open=True)
        self.display_panel.recalculate_button.setEnabled(False)
        self.statusBar().showMessage(tr("Opening Cine; Initializing Photometric Ref90..."))
        self.controller.open(path)
        return True

    def _opened(self, metadata, timing):
        if hasattr(self, 'review_manager') and self.review_manager.active:
            return
        self.metadata = metadata
        self.metadata_panel.set_metadata(metadata, timing)
        self.timeline.set_count(metadata.frame_count)
        self.transport.setEnabled(metadata.frame_count > 0)
        self.session = ViewerSession(metadata.filename, metadata.file_size_bytes, metadata.frame_count)
        if self._pending_session is not None:
            pending, self._pending_session = self._pending_session, None
            if (pending.cine_filename, pending.file_size_bytes, pending.frame_count) != (
                    metadata.filename, metadata.file_size_bytes, metadata.frame_count):
                self._error("Session identity differs from selected Cine; session was not applied")
            else:
                self.session = pending
                if pending.ui_state.get('language') in ('zh_CN', 'en_US'):
                    self.change_language(pending.ui_state['language'])
                self.canvas.set_auto_fit(pending.ui_state.get('auto_fit_to_view', True))
                fps = pending.ui_state.get("review_speed_frames_per_second",
                                           pending.ui_state.get("review_playback_fps", 10))
                if fps in REVIEW_PLAYBACK_FPS:
                    self.transport.fps.setCurrentText(str(fps))
                try:
                    self.display_panel.set_settings(DisplaySettings.from_dict(
                        pending.ui_state.get("display", {"mode": MODE})))
                except (TypeError, ValueError) as error:
                    self.display_panel.reset()
                    self._error(tr("Invalid session display settings; using Raw: ") + str(error))
                self._update_bookmarks()
        self._photometric_changed()
        self.navigate(self.session.last_frame)

    def _photometric_changed(self):
        self.display_panel.set_photometric(self.controller.photometric,
                                           self.controller.photometric_error,
                                           cine_open=self.metadata is not None)
        self.refresh_display()

    def navigate(self, index):
        self.pause()
        if self.metadata is None:
            return
        index = self.controller.state.clamp(index)
        if self.review_manager.active and (self.review_manager.cine_id, index) not in self.review_manager.provider.metadata:
            self.controller.request_frame(index)
            return
        cancelled = self.editor.frame_will_change()
        if self.current_record is not None:
            self.timeline.set_frame(self.current_record.frame_index)
        self.statusBar().showMessage((tr("Unfinished drawing cancelled; ") if cancelled else "") + tr("Loading frame ") + str(index))
        self.controller.request_frame(index)

    def step(self, amount):
        if self.review_manager.active and abs(amount) == 1:
            self.review_manager.adjacent(1 if amount > 0 else -1)
            return
        self.navigate(self.controller.state.frame_index + amount)

    def _frame_ready(self, index, image, record):
        if self.timeline.debounce.isActive():
            return  # A newer slider intent is waiting for debounce; do not cancel it.
        self.raw_image, self.current_record = image, record
        self.refresh_display()
        self.timeline.set_frame(index)
        self.transport.frame_label.setText(f"{index} / {self.metadata.frame_count - 1}")
        self.metadata_panel.set_frame(record)
        value = "unknown" if record.timestamp_s is None else f"{record.timestamp_s:.9f} s"
        self.time_label.setText(tr(f"Frame: {index} / {self.metadata.frame_count - 1}    Relative timestamp: {value}    {record.timing_status.value}"))
        self.session.last_frame = index
        self.editor.frame_loaded()
        self.refresh_overlays()
        if self.controller.photometric_error:
            self.statusBar().showMessage(tr("PHOTOMETRIC_REFERENCE_FAILED: Photometric Ref90 unavailable; Raw display used."))
        if self.review_clock.active:
            self._review_status()
        if index == self._playback_last_frame():
            self.pause()

    def refresh_display(self, settings=None):
        settings = self.display_panel.settings
        if settings.mode == MODE and self.controller.photometric_error:
            # Keep the user's Raw/Manual/Auto override when a background reference fails.
            self.display_panel.show_raw()
            self.statusBar().showMessage(
                tr("PHOTOMETRIC_REFERENCE_FAILED: Photometric Ref90 unavailable; Raw display used."))
            return
        mode = self.display_panel.mode.currentText()
        if settings.mode == "auto_percentile":
            mode += f" {settings.percentile_low:g}–{settings.percentile_high:g}%"
        self.display_label.setText(tr("Display: ") + mode)
        if self.raw_image is None:
            return
        result = render_display(self.raw_image, settings, photometric=self.controller.photometric)
        self.canvas.set_image(result.image)
        message = (tr("Raw display reference; zoom/display do not alter scientific pixels.")
                   if settings.mode == "raw" else tr("Display enhancement active — raw scientific pixels unchanged."))
        if settings.mode == MODE:
            message = (tr("Photometric Ref90 active — Cine-locked gain; raw scientific pixels unchanged.")
                       if self.controller.photometric is not None else
                       tr("Initializing Photometric Ref90... Raw display used while waiting."))
        elif settings.mode == "raw" and self.controller.photometric_error:
            message = tr("PHOTOMETRIC_REFERENCE_FAILED: Photometric Ref90 unavailable; Raw display used.")
        self.statusBar().showMessage(message + (" " + result.diagnostic if result.diagnostic else ""))

    def refresh_overlays(self):
        if self.current_record is not None:
            record = self.current_record
            records = [a for layer in self.layers for a in layer.annotations
                       if a.cine_id == record.cine_id and a.frame_index == record.frame_index]
            projections = list(self.editor.projections().values()) if hasattr(self, 'editor') else []
            doc = self.editor.document if hasattr(self, 'editor') else None
            suppressed = doc.support_suppressed_ids(record.frame_index) if doc else set()
            records = [r for r in records if r.annotation_id not in suppressed]
            hidden = self.editor.hidden_ids() if hasattr(self, 'editor') else set()
            records += projections
            colors = record_colors(self.annotation_panel.display_config, records)
            layers = [replace(layer, annotations=[r for r in layer.annotations if r.annotation_id not in suppressed]
                              + (projections if layer.layer_id == 'manual' else []))
                      for layer in self.layers]
            self.canvas.overlays.render(layers, record.cine_id, record.frame_index, colors, hidden)
            self.annotation_panel.set_records(records, colors, hidden, {r.annotation_id for r in projections})
            if hasattr(self, "editor"):
                self.editor.refresh_selection()

    def toggle_play(self):
        if self.review_clock.active:
            self.pause()
        elif self.current_record is not None and self.current_record.frame_index < self._playback_last_frame():
            self.timeline.debounce.stop()
            self.timeline.set_frame(self.current_record.frame_index)
            cancel = getattr(self.controller, 'cancel_frame_requests', None)
            if cancel is not None:
                cancel(self.current_record.frame_index)
            self.editor.frame_will_change()
            self.review_clock.start(self.current_record.frame_index, self.controller.state.playback_fps)
            self.playback.start()
            self.transport.play.setText(tr("Pause"))
            self._review_status()

    def pause(self):
        was_playing = self.review_clock.active
        self.review_clock.stop()
        self.playback.stop()
        self._review_desired = None
        if was_playing and self.current_record is not None:
            cancel = getattr(self.controller, 'cancel_frame_requests', None)
            if cancel is not None:
                cancel(self.current_record.frame_index)
            if not self.editor.ready:
                self.editor.frame_loaded()
        self.transport.play.setText(tr("Play"))

    def set_playback_fps(self, fps):
        if fps not in REVIEW_PLAYBACK_FPS:
            raise ValueError("Unsupported review playback speed")
        self.controller.state.playback_fps = fps
        # Poll at no more than about 60 Hz, regardless of source-frame speed.
        self.playback.setInterval(max(16, round(1000 / fps)))
        if self.review_clock.active and self.current_record is not None:
            self.pause()
            self.toggle_play()

    def _playback_last_frame(self):
        if self.review_manager.active:
            return self.review_manager.provider.available(self.review_manager.cine_id)[-1]
        return self.metadata.frame_count - 1 if self.metadata is not None else 0

    def _review_status(self):
        if self.current_record is None:
            return
        rate = self.controller.state.playback_fps
        text = tr('Review speed: {rate} frames/s | Frame: {frame} / {last}').format(
            rate=rate, frame=self.current_record.frame_index, last=self.metadata.frame_count - 1)
        if rate >= 60:
            text += ' | ' + tr('High-speed frame skipping: enabled')
        self.statusBar().showMessage(text)

    def _tick(self):
        if not self.review_clock.active or self.metadata is None or self.current_record is None:
            return
        desired = self.review_clock.desired_frame(self.metadata.frame_count)
        if self.review_manager.active:
            available = self.review_manager.provider.available(self.review_manager.cine_id)
            desired = available[max(0, bisect_right(available, desired) - 1)]
        self._review_desired = desired  # One replaceable target, not a FIFO.
        # Backpressure: let the admitted decode complete rather than repeatedly
        # invalidating it and starving presentation on slow disks. Manual seeks
        # and Pause still invalidate old tokens. The next idle tick samples the
        # latest clock target, dropping all intermediate unrequested frames.
        if getattr(self.controller, 'busy', False):
            return
        if desired != self.current_record.frame_index:
            self.editor.frame_will_change()
            self.controller.request_frame(desired)
        elif desired >= self._playback_last_frame():
            self.pause()

    def close_cine(self):
        if not self.editor.confirm_discard():
            return False
        self.review_manager.leave()
        self._pending_session = None
        self._reset()
        self.cine_path = None
        self.controller.close()
        return True

    def _error(self, message):
        self.pause()
        self.statusBar().showMessage(tr("Error: ") + message)
        QMessageBox.warning(self, tr("Cine Viewer"), message)

    def add_bookmark(self, checked=False, note="", tags=None):
        if self.current_record is None or self.session is None:
            return
        record = self.current_record
        self.session.bookmarks.append(Bookmark(record.frame_index, record.timestamp_time64,
                                               record.timestamp_s, note, tags or []))
        self._update_bookmarks()

    def _update_bookmarks(self):
        self.bookmarks_list.clear()
        for bookmark in self.session.bookmarks:
            self.bookmarks_list.addItem(f"{bookmark.frame_index}: {bookmark.note} {' '.join(bookmark.tags)}")
            self.bookmarks_list.item(self.bookmarks_list.count() - 1).setData(Qt.ItemDataRole.UserRole, bookmark.frame_index)

    def bookmark_dialog(self):
        if self.current_record is None:
            return
        note, ok = QInputDialog.getText(self, tr("Bookmark"), tr("Note (optional)"))
        if ok:
            tags, ok = QInputDialog.getText(self, tr("Bookmark"), tr("Tags (comma-separated, any strings)"))
            if ok:
                self.add_bookmark(note=note, tags=[s.strip() for s in tags.split(",") if s.strip()])

    def notes_dialog(self):
        if self.session is not None:
            notes, ok = QInputDialog.getMultiLineText(self, tr("Session notes"), tr("Notes"), self.session.notes)
            if ok:
                self.session.notes = notes

    def export_frame(self, path):
        if self.raw_image is None:
            raise ValueError("No loaded frame to export")
        export_png(self.raw_image, Path(path))

    def export_dialog(self):
        if self.current_record is None:
            return
        name = f"{Path(self.metadata.filename).stem}_frame_{self.current_record.frame_index:06d}.png"
        output_dir = Path("outputs/viewer_frames")
        output_dir.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, tr("Export Current Frame"), str(output_dir / name), "PNG (*.png)")
        if path:
            try:
                self.export_frame(path)
                self.statusBar().showMessage("Exported raw frame: " + Path(path).name)
            except Exception as error:
                self._error(str(error))

    def save_session(self, path):
        if self.session is None:
            raise ValueError("No Cine session")
        self.session.ui_state.pop('review_playback_fps', None)
        self.session.ui_state.update(review_speed_frames_per_second=self.controller.state.playback_fps,
                                     language=current_language(),
                                     display=self.display_panel.settings.to_dict(),
                                     auto_fit_to_view=self.canvas.auto_fit_enabled)
        self.session.ui_state["photometric"] = (
            self.controller.photometric.to_dict() if self.controller.photometric is not None else {
                "preset_id": PRESET_ID, "reference_fraction": REFERENCE_FRACTION,
                "photometric_status": "PHOTOMETRIC_REFERENCE_FAILED" if self.controller.photometric_error else "INITIALIZING",
                "error": self.controller.photometric_error})
        self.session.save(path)

    def save_session_dialog(self):
        if self.session is None or self.review_manager.active:
            return
        output_dir = Path("outputs/viewer_sessions")
        output_dir.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, tr("Save Session"), str(output_dir / (self.cine_path.stem + ".json")), "Session JSON (*.json)")
        if path:
            try:
                self.save_session(path)
            except Exception as error:
                self._error(str(error))

    def load_session_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Load Session"), "outputs/viewer_sessions", "Session JSON (*.json)")
        if not path:
            return
        try:
            session = ViewerSession.load(path)
            if self.cine_path is not None and self.cine_path.name == session.cine_filename:
                cine = self.cine_path
            else:
                cine, _ = QFileDialog.getOpenFileName(self, "Locate " + session.cine_filename, "", "Phantom Cine (*.cine)")
            if cine:
                self.open_cine(cine, session)
        except Exception as error:
            self._error(str(error))

    def closeEvent(self, event):
        batch = getattr(getattr(self, 'review_manager', None), 'batch_window', None)
        if batch is not None and batch.busy:
            batch.cancel()
            self.statusBar().showMessage(tr('Cancelling after the current read; completed packages are retained.'))
            event.ignore()
            return
        if hasattr(self, 'review_manager') and self.review_manager.task is not None:
            self.statusBar().showMessage(tr('Wait for annotation package export to finish.'))
            event.ignore()
            return
        if not self.editor.confirm_discard():
            event.ignore()
            return
        if not self.queue_manager.confirm_close():
            event.ignore()
            return
        self.editor.autosave_timer.stop()
        self.editor.cancel()
        self.pause()
        self.controller.shutdown()
        event.accept()
