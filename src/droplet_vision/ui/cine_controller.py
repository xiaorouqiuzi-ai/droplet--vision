"""Serialized worker I/O, coalesced pending requests, and stale-result protection."""
from __future__ import annotations
from PySide6.QtCore import QObject, Signal, Slot, QRunnable, QThreadPool
from ..cine import CineReader
from .frame_cache import FrameCache
from .viewer_state import ViewerState


class _Signals(QObject):
    done = Signal(int, str, object, object)


class _Task(QRunnable):
    def __init__(self, token, kind, work):
        super().__init__()
        self.token, self.kind, self.work = token, kind, work
        self.signals = _Signals()

    def run(self):
        try:
            result = self.work()
        except Exception as error:
            self.signals.done.emit(self.token, self.kind, None, str(error))
        else:
            self.signals.done.emit(self.token, self.kind, result, None)


class CineController(QObject):
    opened = Signal(object, object)
    frame_ready = Signal(int, object, object)
    failed = Signal(str)
    closed = Signal()

    def __init__(self, parent=None, cache_capacity=64, reader_factory=CineReader):
        super().__init__(parent)
        self.state = ViewerState()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self._reader_factory = reader_factory
        self._reader = None
        self.cache = FrameCache(cache_capacity)
        self._task = None
        self._pending = None
        self._shutdown = False

    def _close_worker(self):
        if self._reader is not None:
            self._reader.close()
            self._reader = None
        self.cache.clear()

    def open(self, path):
        self.state.frame_count = 0
        token = self.state.invalidate()

        def work():
            self._close_worker()
            self._reader = self._reader_factory(path)
            return self._reader.metadata, self._reader.timing_summary
        self._schedule(token, "open", work)

    def request_frame(self, index):
        if not self.state.frame_count:
            return
        token = self.state.request(index)
        index = self.state.frame_index

        def work():
            pixels = self.cache.get(index)
            if pixels is None:
                pixels = self._reader.read_frame(index)
                pixels.setflags(write=False)
                self.cache.put(index, pixels)
            return index, pixels, self._reader.build_frame_result(index)
        self._schedule(token, "frame", work)

    def close(self):
        self.state.frame_count = 0
        self._schedule(self.state.invalidate(), "close", self._close_worker)

    def _schedule(self, token, kind, work):
        if self._shutdown:
            return
        self._pending = (token, kind, work)  # at most one newest request is retained
        if self._task is None:
            self._start_pending()

    def _start_pending(self):
        if self._pending is None or self._shutdown:
            return
        token, kind, work = self._pending
        self._pending = None
        self._task = _Task(token, kind, work)
        self._task.signals.done.connect(self._complete)
        self.pool.start(self._task)

    @Slot(int, str, object, object)
    def _complete(self, token, kind, result, error):
        self._task = None
        if not self._shutdown and self.state.accepts(token):
            if error is not None:
                self.failed.emit(error)
            elif kind == "open":
                metadata, timing = result
                self.state.frame_count = metadata.frame_count
                self.opened.emit(metadata, timing)
            elif kind == "frame":
                self.frame_ready.emit(*result)
            else:
                self.closed.emit()
        # A signal handler may already have started a task.
        if self._task is None:
            self._start_pending()

    def shutdown(self):
        self._shutdown = True
        self.state.invalidate()
        self._pending = None
        self.pool.waitForDone()
        self._close_worker()
