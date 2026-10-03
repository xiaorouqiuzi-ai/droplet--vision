"""Sampling parameters have one versioned JSON source of truth."""
from __future__ import annotations
from dataclasses import dataclass, asdict
import hashlib
import json
import math
from pathlib import Path
from typing import Tuple


@dataclass(frozen=True)
class SamplingConfig:
    preset_id: str
    anchor_fractions: Tuple[float, ...]
    max_probe_frames: int
    max_change_peaks: int
    minimum_peak_separation_fraction: float
    minimum_peak_separation_frames: int
    change_metric: str
    anchor_priority: int
    change_peak_priority: int

    def __post_init__(self):
        if not self.preset_id or self.change_metric != "mean_absolute_difference_raw_uint8":
            raise ValueError("Unsupported sampling preset/metric")
        numbers = (*self.anchor_fractions, self.minimum_peak_separation_fraction)
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
               or not 0 <= v <= 1 for v in numbers):
            raise ValueError("Sampling fractions must be finite and in [0, 1]")
        if any(isinstance(v, bool) or not isinstance(v, int) for v in (
                self.max_probe_frames, self.max_change_peaks, self.minimum_peak_separation_frames,
                self.anchor_priority, self.change_peak_priority)):
            raise ValueError("Sampling counts/priorities must be integers")
        if not 2 <= self.max_probe_frames <= 512 or self.max_change_peaks < 0 or self.minimum_peak_separation_frames < 1:
            raise ValueError("Invalid probe/peak bounds; at most 512 coarse probes are supported")

    def to_dict(self):
        result = asdict(self)
        result["anchor_fractions"] = list(self.anchor_fractions)
        return result

    @property
    def sha256(self):
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True).encode()).hexdigest()


def load_sampling_config(path=None) -> SamplingConfig:
    path = Path(path) if path is not None else Path(__file__).resolve().parents[3] / "configs/sampling/frame_sampling_v1.json"
    values = json.loads(path.read_text(encoding="utf-8"))
    values["anchor_fractions"] = tuple(values["anchor_fractions"])
    return SamplingConfig(**values)
