"""Bounded raw-frame LRU; only the serialized reader worker accesses it."""
from collections import OrderedDict
from typing import Any


class FrameCache:
    def __init__(self, capacity: int = 64):
        if capacity < 1:
            raise ValueError("Cache capacity must be positive")
        self.capacity = capacity
        self._items = OrderedDict()

    def get(self, index: int) -> Any:
        if index not in self._items:
            return None
        self._items.move_to_end(index)
        return self._items[index]

    def put(self, index: int, image: Any) -> None:
        self._items[index] = image
        self._items.move_to_end(index)
        while len(self._items) > self.capacity:
            self._items.popitem(last=False)

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)
