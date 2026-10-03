"""Renderer extension interface: records become scene items in pixel coordinates."""
from abc import ABC, abstractmethod


class OverlayRenderer(ABC):
    @abstractmethod
    def render(self, scene, record, color):
        """Return graphics items without editing the annotation record."""
        raise NotImplementedError
