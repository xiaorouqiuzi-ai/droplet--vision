"""Runtime domain for the shared support-template projection resolver."""
from dataclasses import dataclass


@dataclass(frozen=True)
class SupportTemplateScope:
    kind: str = 'cine'
    available_frames: frozenset | range | None = None

    def __post_init__(self):
        if self.kind not in ('cine', 'package'):
            raise ValueError('Unknown support template scope')
        if self.kind == 'package' and self.available_frames is None:
            raise ValueError('Package scope requires an available-frame domain')

    @property
    def enabled_key(self):
        return 'enabled' if self.kind == 'package' else 'apply_entire_cine'

    def contains(self, frame, count):
        return type(frame) is int and 0 <= frame < count and (
            self.available_frames is None or frame in self.available_frames)
