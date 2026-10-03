"""Cine Viewer v1 shell for the future Droplet Annotation Workstation."""
from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QSplitter,
                               QFileDialog, QMessageBox, QLabel, QListWidget, QInputDialog, QDockWidget)
from ..annotations import AnnotationLayer, Bookmark, ViewerSession
from ..annotations.taxonomy import load_taxonomy, default_taxonomy_path
from ..display import DisplaySettings, render_display
from .cine_controller import CineController
from .display import export_png
from .widgets.image_canvas import ImageCanvas
from .widgets.timeline import Timeline
from .widgets.transport_controls import TransportControls
from .panels.metadata_panel import MetadataPanel
from .panels.annotation_panel import AnnotationPanel
from .panels.layer_panel import LayerPanel
from .panels.display_panel import DisplayPanel


class MainWindow(QMainWindow):
    def __init__(self, taxonomy_path=None, parent=None, controller=None):
        super().__init__(parent)
        self.setWindowTitle("Droplet Annotation Workstation — Cine Viewer v1")
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
        splitter = QSplitter()
        self.metadata_panel = MetadataPanel()
        self.canvas = ImageCanvas()
        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.annotation_panel = AnnotationPanel(labels)
        self.layer_panel = LayerPanel(self.layers)
        self.layer_panel.changed.connect(self.refresh_overlays)
        right_layout.addWidget(self.annotation_panel)
        right_layout.addWidget(self.layer_panel)
        right_layout.addWidget(QLabel("Bookmarks (double-click to navigate)"))
        self.bookmarks_list = QListWidget()
        self.bookmarks_list.setMaximumHeight(110)
        self.bookmarks_list.itemDoubleClicked.connect(lambda item: self.navigate(item.data(Qt.ItemDataRole.UserRole)))
        right_layout.addWidget(self.bookmarks_list)
        splitter.addWidget(self.metadata_panel)
        splitter.addWidget(self.canvas)
        splitter.addWidget(right)
        splitter.setSizes([270, 660, 350])
        layout.addWidget(splitter, 1)
        self.timeline = Timeline()
        self.timeline.requested.connect(self.navigate)
        self.transport = TransportControls()
        self.transport.step.connect(self.step)
        self.transport.first.connect(lambda: self.navigate(0))
        self.transport.last.connect(lambda: self.navigate(self.controller.state.frame_count - 1))
        self.transport.toggle_play.connect(self.toggle_play)
        self.transport.fps_changed.connect(self.set_playback_fps)
        self.time_label = QLabel("Relative timestamp: unknown")
        layout.addWidget(self.timeline)
        layout.addWidget(self.transport)
        layout.addWidget(self.time_label)
        self.setCentralWidget(central)
        self.display_panel = DisplayPanel()
        self.display_dock = QDockWidget("Display", self)
        self.display_dock.setObjectName("displayDock")
        self.display_dock.setWidget(self.display_panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.display_dock)
        self.display_label = QLabel("Display: RAW")
        self.statusBar().addPermanentWidget(self.display_label)
        self.display_panel.changed.connect(self.refresh_display)
        self.playback = QTimer(self)
        self.playback.setInterval(100)
        self.playback.timeout.connect(self._tick)
        self.controller.opened.connect(self._opened)
        self.controller.frame_ready.connect(self._frame_ready)
        self.controller.failed.connect(self._error)
        self._menus()
        self.transport.setEnabled(False)
        self.statusBar().showMessage("Open a Cine to begin. Display pixels are separate from scientific raw values.")

    def _action(self, menu, text, callback, shortcut=None):
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(callback)
        menu.addAction(action)
        return action

    def _menus(self):
        file_menu = self.menuBar().addMenu("File")
        self._action(file_menu, "Open Cine...", self.open_dialog, "Ctrl+O")
        self._action(file_menu, "Close Cine", self.close_cine)
        self.export_action = self._action(file_menu, "Export Current Frame...", self.export_dialog, "Ctrl+E")
        self.export_action.setToolTip("Exports raw frame pixels, not display-enhanced preview.")
        self.export_action.setStatusTip(self.export_action.toolTip())
        self._action(file_menu, "Save Session As...", self.save_session_dialog, "Ctrl+S")
        self._action(file_menu, "Load Session...", self.load_session_dialog, "Ctrl+L")
        self._action(file_menu, "Exit", self.close, "Ctrl+Q")
        view = self.menuBar().addMenu("View")
        view.addAction(self.display_dock.toggleViewAction())
        self._action(view, "Raw display", self.display_panel.show_raw, "R")
        self._action(view, "Enhanced display (previous mode)", self.display_panel.show_enhanced, "E")
        self._action(view, "Reset Display", self.display_panel.reset)
        self._action(view, "Fit image", self.canvas.fit_image, "F")
        self._action(view, "Zoom in", lambda: self.canvas.zoom(1.2), "+")
        self._action(view, "Zoom out", lambda: self.canvas.zoom(1 / 1.2), "-")
        for shortcut, delta in [("Left", -1), ("Right", 1), ("Shift+Left", -10),
                                ("Shift+Right", 10), ("PgUp", -100), ("PgDown", 100)]:
            self._action(view, shortcut, lambda checked=False, d=delta: self.step(d), shortcut)
        self._action(view, "First frame", lambda: self.navigate(0), "Home")
        self._action(view, "Last frame", lambda: self.navigate(self.controller.state.frame_count - 1), "End")
        self._action(view, "Review playback", self.toggle_play, "Space")
        annotation = self.menuBar().addMenu("Annotation")
        self._action(annotation, "Bookmark current frame", self.add_bookmark, "B")
        self._action(annotation, "Bookmark with note/tags...", self.bookmark_dialog)
        self._action(annotation, "Session notes...", self.notes_dialog)
        model = self.menuBar().addMenu("Model")
        future = model.addAction("Prediction providers — future extension")
        future.setEnabled(False)
        help_menu = self.menuBar().addMenu("Help")
        self._action(help_menu, "About", lambda: QMessageBox.information(
            self, "Cine Viewer v1", "Read-only Cine review. Timing remains provisional when unresolved.\n"
            "Labels are taxonomy-configured. Geometry editing and model inference are future work."))

    def open_dialog(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Open Cine", "", "Phantom Cine (*.cine)")
        if filename:
            self.open_cine(filename)

    def _reset(self):
        self.pause()
        self.timeline.set_count(0)
        self.transport.setEnabled(False)
        self.canvas.clear_image()
        self.raw_image = self.current_record = self.metadata = self.session = None
        self.display_panel.reset()
        self.time_label.setText("Relative timestamp: unknown")
        self.metadata_panel.setPlainText("No Cine open")
        self.bookmarks_list.clear()
        for layer in self.layers:
            layer.annotations.clear()
        self.annotation_panel.set_records([])

    def open_cine(self, path, session=None):
        self._reset()
        self.cine_path = Path(path)
        self._pending_session = session
        self.statusBar().showMessage("Opening Cine...")
        self.controller.open(path)

    def _opened(self, metadata, timing):
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
                fps = pending.ui_state.get("review_playback_fps", 10)
                if fps in (1, 2, 5, 10, 15, 20, 30):
                    self.transport.fps.setCurrentText(str(fps))
                try:
                    self.display_panel.set_settings(DisplaySettings.from_dict(pending.ui_state.get("display", {})))
                except (TypeError, ValueError) as error:
                    self.display_panel.reset()
                    self._error("Invalid session display settings; using Raw: " + str(error))
                self._update_bookmarks()
        self.navigate(self.session.last_frame)

    def navigate(self, index):
        if self.metadata is None:
            return
        index = self.controller.state.clamp(index)
        self.timeline.set_frame(index)
        self.statusBar().showMessage("Loading frame " + str(index))
        self.controller.request_frame(index)

    def step(self, amount):
        self.navigate(self.controller.state.frame_index + amount)

    def _frame_ready(self, index, image, record):
        if self.timeline.debounce.isActive():
            return  # A newer slider intent is waiting for debounce; do not cancel it.
        self.raw_image, self.current_record = image, record
        self.refresh_display()
        self.timeline.set_frame(index)
        self.metadata_panel.set_frame(record)
        value = "unknown" if record.timestamp_s is None else f"{record.timestamp_s:.9f} s"
        self.time_label.setText(f"Frame: {index} / {self.metadata.frame_count - 1}    Relative timestamp: {value}    {record.timing_status.value}")
        self.session.last_frame = index
        self.refresh_overlays()
        if index == self.metadata.frame_count - 1:
            self.pause()

    def refresh_display(self, settings=None):
        settings = self.display_panel.settings
        mode = settings.mode.upper()
        if settings.mode == "auto_percentile":
            mode = f"AUTO {settings.percentile_low:g}–{settings.percentile_high:g}%"
        self.display_label.setText("Display: " + mode)
        if self.raw_image is None:
            return
        result = render_display(self.raw_image, settings)
        self.canvas.set_image(result.image)
        message = ("Raw display reference; zoom/display do not alter scientific pixels."
                   if settings.mode == "raw" else "Display enhancement active — raw scientific pixels unchanged.")
        self.statusBar().showMessage(message + (" " + result.diagnostic if result.diagnostic else ""))

    def refresh_overlays(self):
        if self.current_record is not None:
            record = self.current_record
            self.canvas.overlays.render(self.layers, record.cine_id, record.frame_index)
            self.annotation_panel.set_records([a for layer in self.layers for a in layer.annotations
                                               if a.cine_id == record.cine_id and a.frame_index == record.frame_index])

    def toggle_play(self):
        if self.playback.isActive():
            self.pause()
        elif self.metadata is not None and self.controller.state.frame_index < self.metadata.frame_count - 1:
            self.playback.start()
            self.transport.play.setText("Pause")

    def pause(self):
        self.playback.stop()
        self.transport.play.setText("Play")

    def set_playback_fps(self, fps):
        if fps not in (1, 2, 5, 10, 15, 20, 30):
            raise ValueError("Unsupported review playback speed")
        self.controller.state.playback_fps = fps
        self.playback.setInterval(round(1000 / fps))

    def _tick(self):
        if self.metadata is None or self.controller.state.frame_index >= self.metadata.frame_count - 1:
            self.pause()
        elif not self.timeline.debounce.isActive() and self.current_record is not None and self.current_record.frame_index == self.controller.state.frame_index:
            self.step(1)  # do not race ahead when disk decoding is slower than review playback

    def close_cine(self):
        self._pending_session = None
        self._reset()
        self.cine_path = None
        self.controller.close()

    def _error(self, message):
        self.pause()
        self.statusBar().showMessage("Error: " + message)
        QMessageBox.warning(self, "Cine Viewer", message)

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
        note, ok = QInputDialog.getText(self, "Bookmark", "Note (optional)")
        if ok:
            tags, ok = QInputDialog.getText(self, "Bookmark", "Tags (comma-separated, any strings)")
            if ok:
                self.add_bookmark(note=note, tags=[s.strip() for s in tags.split(",") if s.strip()])

    def notes_dialog(self):
        if self.session is not None:
            notes, ok = QInputDialog.getMultiLineText(self, "Session notes", "Notes", self.session.notes)
            if ok:
                self.session.notes = notes

    def export_frame(self, path):
        if self.raw_image is None:
            raise ValueError("No loaded frame to export")
        export_png(self.raw_image, Path(path))

    def export_dialog(self):
        if self.current_record is None:
            return
        name = f"{self.cine_path.stem}_frame_{self.current_record.frame_index:06d}.png"
        output_dir = Path("outputs/viewer_frames")
        output_dir.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, "Export Current Frame", str(output_dir / name), "PNG (*.png)")
        if path:
            try:
                self.export_frame(path)
                self.statusBar().showMessage("Exported raw frame: " + Path(path).name)
            except Exception as error:
                self._error(str(error))

    def save_session(self, path):
        if self.session is None:
            raise ValueError("No Cine session")
        self.session.ui_state.update(review_playback_fps=self.controller.state.playback_fps,
                                     display=self.display_panel.settings.to_dict())
        self.session.save(path)

    def save_session_dialog(self):
        if self.session is None:
            return
        output_dir = Path("outputs/viewer_sessions")
        output_dir.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, "Save Session", str(output_dir / (self.cine_path.stem + ".json")), "Session JSON (*.json)")
        if path:
            try:
                self.save_session(path)
            except Exception as error:
                self._error(str(error))

    def load_session_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Session", "outputs/viewer_sessions", "Session JSON (*.json)")
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
        self.pause()
        self.controller.shutdown()
        event.accept()
