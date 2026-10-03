"""Small request-token state independent of Qt widgets."""
from dataclasses import dataclass


@dataclass
class ViewerState:
    frame_count: int = 0
    frame_index: int = 0
    request_token: int = 0
    playback_fps: int = 10

    def clamp(self, index: int) -> int:
        return max(0, min(int(index), max(0, self.frame_count - 1)))

    def invalidate(self) -> int:
        self.request_token += 1
        return self.request_token

    def request(self, index: int) -> int:
        self.frame_index = self.clamp(index)
        return self.invalidate()

    def accepts(self, token: int) -> bool:
        return token == self.request_token
