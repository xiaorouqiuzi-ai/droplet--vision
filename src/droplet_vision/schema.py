"""Transport interfaces; no segmentation, array, or GPU dependency.

None means unavailable or unmeasured, never a measured zero. Mask adapters
must document coordinate systems, shape, instance IDs and representation in
metadata. State confidence is not physical measurement confidence.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .enums import DropletState, TimingStatus


@dataclass
class FrameResult:
    """One decoded frame and its derived observations.

    timestamp_s is relative to a documented origin. Preserve original TIME64
    integers even if a convenient floating-point timestamp is also supplied.
    """

    cine_id: str
    frame_index: int
    timestamp_s: Optional[float] = None
    parent_mask: Optional[Any] = None
    cavity_masks: Optional[Any] = None
    daughter_masks: Optional[Any] = None
    interference_masks: Optional[Any] = None
    state: Optional[DropletState] = None
    state_confidence: Optional[float] = None
    timestamp_time64: Optional[int] = None
    fps_header: Optional[float] = None
    fps_timestamp: Optional[float] = None
    fps_ratio: Optional[float] = None
    timing_status: TimingStatus = TimingStatus.TIMING_UNKNOWN
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FrameMetrics:
    """Optional 2D measurements; area fields use square pixels.

    Length fields use pixels. Fractions/circularity are dimensionless;
    intensity units and preprocessing must be recorded with the frame.
    """

    parent_area_px: Optional[float] = None
    parent_perimeter_px: Optional[float] = None
    parent_deq_px: Optional[float] = None
    parent_circularity: Optional[float] = None
    cavity_count: Optional[int] = None
    cavity_total_area_px: Optional[float] = None
    cavity_largest_area_px: Optional[float] = None
    cavity_fraction: Optional[float] = None
    minimum_shell_thickness_px: Optional[float] = None
    daughter_count: Optional[int] = None
    daughter_mean_deq_px: Optional[float] = None
    daughter_median_deq_px: Optional[float] = None
    mean_intensity: Optional[float] = None
    intensity_std: Optional[float] = None
