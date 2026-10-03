"""Portable queue items; no images or physical-event classification."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import List, Optional

STATUSES = ("PENDING", "IN_PROGRESS", "DONE", "SKIPPED", "NEEDS_REVIEW")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def relative_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or "\x00" in value:
        raise ValueError("Use a portable relative POSIX path")
    if PureWindowsPath(value).drive or PurePosixPath(value).is_absolute() or any(p in ("", ".", "..") for p in value.split("/")):
        raise ValueError("Absolute paths and traversal are not allowed")
    return value


def resolve_relative(root, value: str) -> Path:
    root = Path(root).resolve()
    path = (root / relative_path(value)).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Resolved path escapes its root")
    return path


def stable_item_id(cine_path: str, index: int) -> str:
    return hashlib.sha256(f"{relative_path(cine_path)}:{index}".encode("utf-8")).hexdigest()[:24]


@dataclass
class AnnotationQueueItem:
    relative_cine_path: str
    cine_id: str
    cine_filename: str
    frame_index: int
    frame_count: int
    frame_fraction: float
    raw_time64: Optional[int]
    relative_timestamp_s: Optional[float]
    timing_status: str
    sample_reasons: List[str]
    change_score: Optional[float] = None
    priority: int = 0
    status: str = "PENDING"
    notes: str = ""
    annotation_document: Optional[str] = None
    coarse_left: Optional[int] = None
    coarse_right: Optional[int] = None
    local_peak_previous_frame: Optional[int] = None
    local_peak_frame: Optional[int] = None
    cine_file_size: Optional[int] = None
    cine_mtime_ns: Optional[int] = None
    item_id: str = ""
    created_at: str = field(default_factory=now)
    updated_at: str = field(default_factory=now)

    def __post_init__(self):
        relative_path(self.relative_cine_path)
        if PurePosixPath(self.relative_cine_path).name != self.cine_filename or not self.cine_id:
            raise ValueError("Invalid Cine identity")
        if any(isinstance(v, bool) or not isinstance(v, int) for v in (self.frame_index, self.frame_count)) or not 0 <= self.frame_index < self.frame_count:
            raise ValueError("Invalid frame range")
        expected = self.frame_index / (self.frame_count - 1) if self.frame_count > 1 else 0.0
        if not math.isfinite(self.frame_fraction) or not math.isclose(expected, self.frame_fraction):
            raise ValueError("Incorrect frame fraction")
        expected_id = stable_item_id(self.relative_cine_path, self.frame_index)
        if self.item_id and self.item_id != expected_id:
            raise ValueError("Item ID does not match Cine/frame")
        self.item_id = expected_id
        if self.status not in STATUSES:
            raise ValueError("Invalid queue status")
        if self.annotation_document is not None:
            relative_path(self.annotation_document)
        if not self.sample_reasons or len(set(self.sample_reasons)) != len(self.sample_reasons):
            raise ValueError("Missing or duplicate sampling reasons")
        for reason in self.sample_reasons:
            if reason == "change_peak":
                continue
            if not reason.startswith("anchor_") or not 0 <= float(reason[7:]) <= 1:
                raise ValueError("Only anchor fractions and change_peak reasons are supported")
        if self.change_score is not None and (not math.isfinite(self.change_score) or not 0 <= self.change_score <= 1):
            raise ValueError("Invalid change score")
        if self.relative_timestamp_s is not None and not math.isfinite(self.relative_timestamp_s):
            raise ValueError("Invalid timestamp")

    def to_dict(self):
        return asdict(self)
