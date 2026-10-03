"""Display-only settings; no Qt, Cine or scientific measurement dependency."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from numbers import Real
from typing import Any, Dict


@dataclass(frozen=True)
class DisplaySettings:
    mode: str = "raw"
    brightness: float = 0.0
    contrast: float = 1.0
    gamma: float = 1.0
    percentile_low: float = 1.0
    percentile_high: float = 99.0

    def __post_init__(self):
        # Mode is an open identifier; availability is checked by the renderer registry.
        if not isinstance(self.mode, str) or not self.mode.strip():
            raise ValueError("Display mode must be a nonempty string")
        for name in ("brightness", "contrast", "gamma", "percentile_low", "percentile_high"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(value):
                raise ValueError(name + " must be a finite number")
            object.__setattr__(self, name, float(value))
        if not -1 <= self.brightness <= 1:
            raise ValueError("Brightness must be between -1 and 1")
        if not .25 <= self.contrast <= 4:
            raise ValueError("Contrast must be between 0.25 and 4")
        if not .2 <= self.gamma <= 5:
            raise ValueError("Gamma must be between 0.2 and 5")
        if not 0 <= self.percentile_low < self.percentile_high <= 100:
            raise ValueError("Percentiles must satisfy 0 <= low < high <= 100")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> DisplaySettings:
        return cls(**value)
