"""Whitelisted core metadata, independent of the PIMS import."""

from __future__ import annotations

import math
from dataclasses import dataclass, field, fields
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


def _json_safe(value: Any) -> Any:
    if isinstance(value, Enum):
        return _json_safe(value.value)
    # Check before builtins: numpy.float64/str_ can subclass float/str.
    if type(value).__module__.startswith("numpy") and getattr(value, "ndim", None) == 0:
        return _json_safe(value.item())
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").rstrip("\x00")
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    raise TypeError("Unsupported metadata value type: " + type(value).__name__)


@dataclass
class CineMetadata:
    path: str = ""
    filename: str = ""
    file_size_bytes: Optional[int] = None
    frame_count: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    bit_depth: Optional[int] = None
    pixel_dtype: Optional[str] = None
    compression: Optional[int] = None
    fps_header: Optional[float] = None
    shutter_ns: Optional[int] = None
    post_trigger: Optional[int] = None
    frame_delay_ns: Optional[int] = None
    serial: Optional[int] = None
    camera_version: Optional[int] = None
    firmware_version: Optional[int] = None
    software_version: Optional[int] = None
    recording_time_zone: Optional[int] = None
    cfa: Optional[int] = None
    trigger_time64: Optional[int] = None
    trigger_datetime: Optional[str] = None
    trigger_second_fraction: Optional[float] = None
    first_image_no: Optional[int] = None
    timestamp_count: int = 0
    d_frame_rate: Optional[float] = None
    f_decimation: Optional[float] = None
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {item.name: _json_safe(getattr(self, item.name)) for item in fields(self)}


def _extract_metadata(path: Path, backend: Any, timestamp_count: int) -> CineMetadata:
    setup = backend.setup_fields_dict
    bitmap = backend.bitmapinfo_dict
    header = backend.header_dict
    trigger = backend.trigger_time
    result = CineMetadata(
        path=str(path), filename=path.name, file_size_bytes=path.stat().st_size,
        frame_count=len(backend), width=bitmap["bi_width"], height=bitmap["bi_height"],
        bit_depth=setup.get("real_bpp") or bitmap.get("bi_bit_count"),
        pixel_dtype=str(backend.pixel_type), compression=backend.compression,
        fps_header=backend.frame_rate, timestamp_count=timestamp_count,
        trigger_time64=header.get("trigger_time"),
        trigger_datetime=_json_safe(trigger.get("datetime")),
        trigger_second_fraction=trigger.get("second_fraction"),
        first_image_no=header.get("first_image_no"),
        notes=["d_frame_rate: not exposed by current PIMS parser",
               "f_decimation: not exposed by current PIMS parser",
               "trigger_datetime uses PIMS host-local datetime; no timezone correction applied",
               "bit_depth uses SETUP real_bpp when nonzero, otherwise BITMAP bi_bit_count"],
    )
    for key in ("shutter_ns", "post_trigger", "frame_delay_ns", "serial", "camera_version",
                "firmware_version", "software_version", "recording_time_zone", "cfa"):
        setattr(result, key, setup.get(key))
    return result
