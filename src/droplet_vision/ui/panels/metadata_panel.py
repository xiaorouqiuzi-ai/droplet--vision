from ..i18n import tr
from PySide6.QtWidgets import QPlainTextEdit


class MetadataPanel(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMinimumWidth(245)
        self._base = tr("No Cine open")
        self.setPlainText(self._base)

    def set_metadata(self, metadata, timing):
        self._base = "\n".join([
            metadata.filename, tr("Frames: ") + str(metadata.frame_count),
            tr(f"Resolution: {metadata.width} × {metadata.height}"),
            tr("Dtype: ") + str(metadata.pixel_dtype), tr("Compression: ") + str(metadata.compression),
            tr("Header FPS: ") + str(timing.fps_header),
            tr("TIME64-derived FPS: ") + (f"{timing.fps_timestamp:.6f}" if timing.fps_timestamp else "unknown"),
            tr("FPS ratio: ") + str(timing.fps_ratio), tr("Timing status: ") + timing.timing_status.value,
            tr("Shutter ns: ") + str(metadata.shutter_ns), tr("Camera serial: ") + str(metadata.serial),
            tr("Camera version: ") + str(metadata.camera_version), tr("Firmware: ") + str(metadata.firmware_version),
            tr("Software: ") + str(metadata.software_version)])
        self.setPlainText(self._base)

    def set_frame(self, record):
        elapsed = "unknown" if record.timestamp_s is None else f"{record.timestamp_s:.9f} s"
        self.setPlainText(self._base + tr(f"\n\nFrame index: {record.frame_index}\nRaw TIME64: {record.timestamp_time64}\nRelative timestamp: {elapsed}"))
