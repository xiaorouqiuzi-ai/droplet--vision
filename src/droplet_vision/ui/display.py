"""Display conversion never changes scientific pixels; PNG exports use raw data."""
from .i18n import tr
from pathlib import Path
import numpy as np
from PySide6.QtGui import QImage


def to_qimage(raw: np.ndarray) -> QImage:
    if raw.ndim == 2 and raw.dtype == np.uint16:
        display = (raw // 256).astype(np.uint8)  # fixed full-range display mapping only
    elif raw.dtype == np.uint8:
        display = raw
    else:
        raise ValueError("Viewer supports 2D uint8/uint16 and RGB uint8")
    display = np.ascontiguousarray(display)
    if display.ndim == 2:
        fmt = QImage.Format.Format_Grayscale8
    elif display.ndim == 3 and display.shape[2] == 3 and display.dtype == np.uint8:
        fmt = QImage.Format.Format_RGB888
    else:
        raise ValueError("Unsupported image shape")
    height, width = display.shape[:2]
    return QImage(display.data, width, height, display.strides[0], fmt).copy()


def export_png(raw: np.ndarray, path: Path) -> None:
    from PIL import Image
    path = Path(path)
    if path.suffix.lower() != ".png" or path.resolve().suffix.lower() != ".png":
        raise ValueError(tr("Frame export must use a .png destination"))
    if not (raw.ndim == 2 and raw.dtype in (np.uint8, np.uint16) or
            raw.ndim == 3 and raw.shape[2] == 3 and raw.dtype == np.uint8):
        raise ValueError("Unsupported raw export format")
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(raw).save(path, format="PNG")
