"""Frame-level judgments, separate from spatial annotations and their layers."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
import math
from typing import Optional
from uuid import uuid4
from .schema import _now, _json_copy
from .scheme import load_state_schema


@dataclass(frozen=True)
class FrameStateRecord:
    cine_id: str
    frame_index: int
    raw_time64: Optional[int] = None
    relative_timestamp_s: Optional[float] = None
    state_ids: tuple = ()
    uncertain: bool = False
    notes: str = ''
    source: str = 'manual'
    review_status: str = 'unreviewed'
    record_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    derived_from: Optional[str] = None

    def __post_init__(self):
        schema = load_state_schema()
        ids = [row['state_id'] for row in schema['states']]
        supplied = tuple(self.state_ids)
        if len(set(supplied)) != len(supplied) or not set(supplied) <= set(ids):
            raise ValueError('Invalid frame state IDs (quality flags are separate)')
        if schema['exclusive_state_id'] in supplied and len(supplied) > 1:
            raise ValueError('Simple evaporation is exclusive in the v1.3 workflow')
        if (not self.cine_id or not self.record_id or type(self.frame_index) is not int or self.frame_index < 0
                or type(self.uncertain) is not bool or not isinstance(self.notes, str)):
            raise ValueError('Invalid frame state identity/quality')
        if self.raw_time64 is not None and (type(self.raw_time64) is not int or not 0 <= self.raw_time64 < 2**64):
            raise ValueError('Invalid raw TIME64')
        if self.relative_timestamp_s is not None and not math.isfinite(self.relative_timestamp_s):
            raise ValueError('Invalid relative timestamp')
        if self.source not in ('manual', 'model', 'imported') or self.review_status not in (
                'unreviewed', 'accepted', 'edited', 'rejected', 'ground_truth'):
            raise ValueError('Invalid provenance')
        object.__setattr__(self, 'state_ids', tuple(i for i in ids if i in supplied))

    def to_dict(self):
        value = asdict(self)
        value['quality'] = {'uncertain': value.pop('uncertain')}
        return _json_copy(value)

    @classmethod
    def from_dict(cls, value):
        value = _json_copy(value)
        value['uncertain'] = value.pop('quality')['uncertain']
        return cls(**value)
