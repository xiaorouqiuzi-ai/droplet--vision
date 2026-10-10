"""Wall-clock browsing only: never derives or changes experimental timestamps."""
from math import floor
from time import monotonic


class ReviewPlayback:
    def __init__(self, now=monotonic):
        self.now = now
        self.active = False
        self.start_frame = 0
        self.started_at = 0.0
        self.rate = 10

    def start(self, displayed_frame, rate):
        self.start_frame = displayed_frame
        self.rate = rate
        self.started_at = self.now()
        self.active = True

    def stop(self):
        self.active = False

    def desired_frame(self, frame_count):
        elapsed = max(0.0, self.now() - self.started_at)
        return min(max(0, frame_count - 1),
                   self.start_frame + floor(elapsed * self.rate))
