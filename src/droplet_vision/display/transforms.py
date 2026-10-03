"""Pure NumPy display transforms. Inputs and scientific data are never modified."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Tuple
import numpy as np
from .settings import DisplaySettings


@dataclass
class DisplayResult:
    image: np.ndarray
    diagnostic: str = ""


def _raw(image: np.ndarray, settings: DisplaySettings) -> DisplayResult:
    return DisplayResult(image.copy())


def _manual(image: np.ndarray, settings: DisplaySettings) -> DisplayResult:
    values = image.astype(np.float64) / 255.0
    values = (values - .5) * settings.contrast + .5 + settings.brightness
    values = np.power(np.clip(values, 0, 1), settings.gamma)
    return DisplayResult(np.rint(values * 255).astype(np.uint8))


def _percentile(image: np.ndarray, settings: DisplaySettings) -> DisplayResult:
    low, high = np.percentile(image, [settings.percentile_low, settings.percentile_high])
    if high <= low:
        return DisplayResult(image.copy(), "Insufficient display percentile range; raw reference retained.")
    values = (image.astype(np.float64) - low) / (high - low)
    return DisplayResult(np.rint(np.clip(values, 0, 1) * 255).astype(np.uint8))


# Future display backends can register without changing the settings schema.
_MODES: Dict[str, Tuple[str, Callable[[np.ndarray, DisplaySettings], DisplayResult]]] = {
    "raw": ("Raw", _raw),
    "manual": ("Manual", _manual),
    "auto_percentile": ("Auto contrast", _percentile),
}


def register_display_mode(mode: str, title: str, transform: Callable) -> None:
    if not isinstance(mode, str) or not mode.strip() or not title or not callable(transform):
        raise ValueError("Display backend requires an ID, title and callable")
    if mode in _MODES:
        raise ValueError("Display mode already registered")
    _MODES[mode] = (title, transform)


def display_modes() -> Dict[str, str]:
    return {mode: value[0] for mode, value in _MODES.items()}


def render_display(image: np.ndarray, settings: DisplaySettings) -> DisplayResult:
    """Return independent uint8 pixels and display-only diagnostics.

    uint16 grayscale retains the existing fixed //256 reference mapping before
    enhancement. RGB uses component-wise manual operations and shared percentiles
    across all channels. There is no resampling, color inference or raw mutation.
    """
    if not isinstance(image, np.ndarray) or not image.size:
        raise ValueError("Display input must be a nonempty ndarray")
    if image.ndim == 2 and image.dtype == np.uint16:
        reference = (image // 256).astype(np.uint8)
    elif image.dtype == np.uint8 and (image.ndim == 2 or image.ndim == 3 and image.shape[2] == 3):
        reference = image.copy()
    else:
        raise ValueError("Display supports grayscale uint8/uint16 and RGB uint8")
    if settings.mode not in _MODES:
        raise ValueError("Unavailable display mode: " + settings.mode)
    result = _MODES[settings.mode][1](reference, settings)
    if result.image.dtype != np.uint8 or result.image.shape != image.shape:
        raise ValueError("Display backend must preserve shape and return uint8")
    # Even extension backends only receive a private copy; output is independently owned.
    return DisplayResult(np.array(result.image, copy=True, order="C"), result.diagnostic)


def apply_display_transform(image: np.ndarray, settings: DisplaySettings) -> np.ndarray:
    return render_display(image, settings).image
