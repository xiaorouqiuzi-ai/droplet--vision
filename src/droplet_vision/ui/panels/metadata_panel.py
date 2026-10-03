from PySide6.QtWidgets import QPlainTextEdit


class MetadataPanel(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMinimumWidth(245)
        self._base = "No Cine open"
        self.setPlainText(self._base)

    def set_metadata(self, metadata, timing):
        self._base = "\n".join([
            metadata.filename, "Frames: " + str(metadata.frame_count),
            f"Resolution: {metadata.width} × {metadata.height}",
            "Dtype: " + str(metadata.pixel_dtype), "Compression: " + str(metadata.compression),
            "Header FPS: " + str(timing.fps_header),
            "TIME64-derived FPS: " + (f"{timing.fps_timestamp:.6f}" if timing.fps_timestamp else "unknown"),
            "FPS ratio: " + str(timing.fps_ratio), "Timing status: " + timing.timing_status.value,
            "Shutter ns: " + str(metadata.shutter_ns), "Camera serial: " + str(metadata.serial),
            "Camera version: " + str(metadata.camera_version), "Firmware: " + str(metadata.firmware_version),
            "Software: " + str(metadata.software_version)])
        self.setPlainText(self._base)

    def set_frame(self, record):
        elapsed = "unknown" if record.timestamp_s is None else f"{record.timestamp_s:.9f} s"
        self.setPlainText(self._base + f"\n\nFrame index: {record.frame_index}\nRaw TIME64: {record.timestamp_time64}\nRelative timestamp: {elapsed}")
