"""Qt-free, open-label annotation records in image pixel coordinates.

Origin is top-left; x is column and y is row, independent of display zoom.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4
import json

GEOMETRY_TYPES = ("point", "polyline", "polygon", "bbox", "ellipse", "mask", "keypoints")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, allow_nan=False))


@dataclass
class AnnotationLabel:
    label_id: str
    display_name: str
    group: Optional[str] = None
    allowed_geometry_types: List[str] = field(default_factory=lambda: list(GEOMETRY_TYPES))
    enabled: bool = True
    attributes: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.label_id or not self.display_name:
            raise ValueError("Label ID and display name must not be empty")
        if not set(self.allowed_geometry_types).issubset(GEOMETRY_TYPES):
            raise ValueError("Unknown geometry type in label")


@dataclass
class AnnotationRecord:
    cine_id: str
    frame_index: int
    label_id: str
    geometry_type: str
    geometry: Dict[str, Any]
    annotation_id: str = field(default_factory=lambda: str(uuid4()))
    source: str = "manual"
    model_id: Optional[str] = None
    confidence: Optional[float] = None
    review_status: str = "unreviewed"
    reviewer: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    derived_from: Optional[str] = None

    def __post_init__(self):
        if not self.label_id or not self.cine_id or self.frame_index < 0:
            raise ValueError("Annotation requires cine/label identity and nonnegative frame index")
        if self.geometry_type not in GEOMETRY_TYPES:
            raise ValueError("Unsupported geometry type")
        if self.source not in ("manual", "model", "imported"):
            raise ValueError("Invalid annotation source")
        if self.review_status not in ("unreviewed", "accepted", "edited", "rejected", "ground_truth"):
            raise ValueError("Invalid review status")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("Confidence must be in [0, 1]")
        _json_copy(self.geometry)

    def to_dict(self) -> Dict[str, Any]:
        return _json_copy(asdict(self))

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> AnnotationRecord:
        return cls(**_json_copy(value))


@dataclass
class AnnotationLayer:
    layer_id: str
    name: str
    role: str = "manual"
    visible: bool = True
    locked: bool = False
    annotations: List[AnnotationRecord] = field(default_factory=list)

    def __post_init__(self):
        if self.role not in ("prediction", "manual", "reviewed", "ground_truth", "measurement", "auxiliary"):
            raise ValueError("Invalid layer role")

    def to_dict(self) -> Dict[str, Any]:
        return _json_copy(asdict(self))

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> AnnotationLayer:
        value = _json_copy(value)
        value["annotations"] = [AnnotationRecord.from_dict(row) for row in value.get("annotations", [])]
        return cls(**value)
