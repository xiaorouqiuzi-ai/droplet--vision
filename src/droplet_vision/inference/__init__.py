"""Backend-neutral future prediction interface; no model packages imported."""
from abc import ABC, abstractmethod
from typing import Any
from ..annotations import AnnotationLayer


class PredictionProvider(ABC):
    @abstractmethod
    def predict(self, cine_id: str, frame_index: int, image: Any) -> AnnotationLayer:
        """Return a prediction layer with model provenance; never modify image."""
        raise NotImplementedError
