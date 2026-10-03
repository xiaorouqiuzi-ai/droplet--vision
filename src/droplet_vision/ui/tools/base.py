"""Extensible tool registry; tools submit immutable-history undo commands."""
from abc import ABC, abstractmethod


class AnnotationTool(ABC):
    def activate(self, canvas):
        self.canvas = canvas

    def deactivate(self):
        self.cancel()

    def mouse_press(self, image_position):
        pass

    def mouse_move(self, image_position):
        pass

    def mouse_release(self, image_position):
        pass

    def mouse_double_click(self, image_position):
        pass

    def backspace(self):
        pass

    @abstractmethod
    def commit(self):
        """Return a new annotation/command; never overwrite prediction records."""
        raise NotImplementedError

    def cancel(self):
        pass


class ToolRegistry:
    def __init__(self):
        self._factories = {}

    def register(self, tool_id, factory):
        if tool_id in self._factories:
            raise ValueError("Duplicate tool ID")
        self._factories[tool_id] = factory

    def create(self, tool_id):
        return self._factories[tool_id]()
