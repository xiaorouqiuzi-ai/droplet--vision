"""Qt-free, Cine-locked display reference. Never alters scientific pixels."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from math import isclose, isfinite
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np

REFERENCE_FRACTION = 0.03
MODE = "photometric_ref90"
PRESET_ID = "photometric_ref90_v1"


@dataclass(frozen=True)
class PhotometricPreset:
    preset_id: str
    version: int
    sha256: str
    reference_p90: float
    target_fraction: float
    target_p90: float
    gain_min: float
    gain_max: float
    saturation_warning_fraction: float
    severe_saturation_warning_fraction: float
    high_gain_warning: float
    very_high_gain_warning: float


def default_preset_path() -> Path:
    return Path(__file__).resolve().parents[3] / "configs/photometry/photometric_ref90_v1.json"


def load_photometric_preset(path: Optional[Union[str, Path]] = None) -> PhotometricPreset:
    """Load the versioned source-checkout preset; never invent fallback parameters."""
    payload = Path(path or default_preset_path()).read_bytes()
    value = json.loads(payload)
    if (value["preset_id"] != PRESET_ID or value["version"] != 1
            or value["reference_metric"] != "p90"
            or value["normalization"]["type"] != "gain_only"
            or value["output"] != {"dtype": "uint8", "grayscale": True, "preserve_geometry": True}):
        raise ValueError("Unsupported photometric preset contract")
    numbers = {key: value[key] for key in ("reference_p90", "target_fraction", "target_p90")}
    numbers.update({key: value["normalization"][key] for key in ("gain_min", "gain_max")})
    numbers.update({key: value["qc"][key] for key in (
        "saturation_warning_fraction", "severe_saturation_warning_fraction",
        "high_gain_warning", "very_high_gain_warning")})
    if any(isinstance(n, bool) or not isinstance(n, (int, float)) or not isfinite(n) or n <= 0
           for n in numbers.values()):
        raise ValueError("Photometric preset numbers must be finite and positive")
    if (numbers["gain_min"] > numbers["gain_max"]
            or not 0 < numbers["target_fraction"] <= 1
            or not 0 < numbers["reference_p90"] <= 255
            or not isclose(numbers["target_p90"], numbers["reference_p90"] * numbers["target_fraction"])
            or not numbers["saturation_warning_fraction"] < numbers["severe_saturation_warning_fraction"] <= 1
            or numbers["high_gain_warning"] >= numbers["very_high_gain_warning"]):
        raise ValueError("Inconsistent photometric preset parameters")
    return PhotometricPreset(value["preset_id"], value["version"], hashlib.sha256(payload).hexdigest(),
                             **{key: float(number) for key, number in numbers.items()})


def cine_reference_index(frame_count: int) -> int:
    if frame_count <= 0:
        raise ValueError("Cine must contain at least one frame")
    return max(0, min(frame_count - 1, round((frame_count - 1) * REFERENCE_FRACTION)))


@dataclass(frozen=True)
class PhotometricReference:
    preset_id: str
    preset_version: int
    preset_sha256: str
    reference_fraction: float
    reference_frame_index: int
    reference_p90: float
    target_p90: float
    gain_raw: float
    gain_used: float
    norm_255_fraction: float
    photometric_status: str
    warnings: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _check_pixels(image: np.ndarray) -> None:
    if not isinstance(image, np.ndarray) or image.dtype != np.uint8 or image.ndim != 2 or not image.size:
        raise ValueError("Photometric Ref90 requires raw uint8 grayscale pixels")


def apply_locked_gain(image: np.ndarray, reference: PhotometricReference) -> np.ndarray:
    """Apply an already estimated scalar; never estimate statistics on this frame."""
    _check_pixels(image)
    return np.clip(np.rint(image.astype(np.float64) * reference.gain_used), 0, 255).astype(np.uint8)


def estimate_reference(image: np.ndarray, frame_count: int, preset: PhotometricPreset) -> PhotometricReference:
    _check_pixels(image)
    p90 = float(np.percentile(image, 90, method="linear"))
    if p90 <= 0:
        raise ValueError("PHOTOMETRIC_REFERENCE_FAILED: reference P90 must be positive")
    raw_gain = preset.target_p90 / p90
    gain = float(np.clip(raw_gain, preset.gain_min, preset.gain_max))
    warnings = []
    if raw_gain < preset.gain_min:
        warnings.append("GAIN_CLIPPED_LOW")
    if raw_gain > preset.gain_max:
        warnings.append("GAIN_CLIPPED_HIGH")
    for threshold, name in ((preset.high_gain_warning, "HIGH_GAIN_WARNING"),
                            (preset.very_high_gain_warning, "VERY_HIGH_GAIN_WARNING")):
        if gain > threshold:
            warnings.append(name)
    pixels = np.clip(np.rint(image.astype(np.float64) * gain), 0, 255).astype(np.uint8)
    saturation = float(np.mean(pixels == 255))
    for threshold, name in ((preset.saturation_warning_fraction, "SATURATION_WARNING"),
                            (preset.severe_saturation_warning_fraction, "SEVERE_SATURATION_WARNING")):
        if saturation > threshold:
            warnings.append(name)
    return PhotometricReference(
        preset.preset_id, preset.version, preset.sha256, REFERENCE_FRACTION,
        cine_reference_index(frame_count), p90, preset.target_p90, raw_gain, gain,
        saturation, "; ".join(warnings) or "OK", tuple(warnings))
