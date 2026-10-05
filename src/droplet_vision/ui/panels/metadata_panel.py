"""Selectable core metadata rows; never statistics from display pixels."""
from ..i18n import tr
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QGroupBox, QLabel


class MetadataPanel(QWidget):
    GROUPS = (
        ('Image information', [('filename', 'Filename'), ('frame_count', 'Frame count'),
                               ('resolution', 'Resolution'), ('dtype', 'Data type'), ('compression', 'Compression')]),
        ('Timing information', [('fps_header', 'Header FPS'), ('fps_timestamp', 'TIME64-derived FPS'),
                                ('fps_ratio', 'FPS ratio'), ('timing_status', 'Timing status')]),
        ('Camera information', [('shutter_ns', 'Shutter ns'), ('serial', 'Camera serial'),
                                ('camera_version', 'Camera version'), ('firmware', 'Firmware'), ('software', 'Software')]),
        ('Current frame', [('frame_index', 'Frame index'), ('raw_time64', 'Raw TIME64'),
                           ('relative_timestamp', 'Relative timestamp')]),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.values = {}
        for title, fields in self.GROUPS:
            group = QGroupBox(tr(title))
            form = QFormLayout(group)
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            for key, caption in fields:
                value = QLabel()
                value.setObjectName('metadata_' + key)
                value.setTextFormat(Qt.TextFormat.PlainText)
                value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
                value.setWordWrap(key in ('filename', 'timing_status'))
                form.addRow(tr(caption), value)
                self.values[key] = value
            layout.addWidget(group)
        self.clear()

    def clear(self):
        for value in self.values.values():
            value.setText('—')

    def _set(self, **values):
        for key, value in values.items():
            self.values[key].setText(tr('unknown') if value is None else str(value))

    def set_metadata(self, metadata, timing):
        self.clear()
        self._set(filename=metadata.filename, frame_count=metadata.frame_count,
                  resolution=f'{metadata.width} × {metadata.height}', dtype=metadata.pixel_dtype,
                  compression=metadata.compression, fps_header=timing.fps_header,
                  fps_timestamp=None if timing.fps_timestamp is None else f'{timing.fps_timestamp:.6f}',
                  fps_ratio=None if timing.fps_ratio is None else f'{timing.fps_ratio:.9f}',
                  timing_status=timing.timing_status.value, shutter_ns=metadata.shutter_ns,
                  serial=metadata.serial, camera_version=metadata.camera_version,
                  firmware=metadata.firmware_version, software=metadata.software_version)

    def set_frame(self, record):
        self._set(frame_index=record.frame_index, raw_time64=record.timestamp_time64,
                  relative_timestamp=None if record.timestamp_s is None else f'{record.timestamp_s:.9f} s',
                  timing_status=record.timing_status.value)
