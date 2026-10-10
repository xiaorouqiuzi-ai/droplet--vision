"""Serialized worker I/O, coalesced pending requests, and stale-result protection."""
from __future__ import annotations
from PySide6.QtCore import QObject, Signal, Slot, QRunnable, QThreadPool
from ..cine import CineReader
from ..display.photometric import cine_reference_index, estimate_reference, load_photometric_preset
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
    photometric_changed = Signal()

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
        self.photometric = None
        self.photometric_error = None
        self._photometric_revision = 0
        self._pending_reference = None

    def _close_worker(self):
        if self._reader is not None:
            self._reader.close()
            self._reader = None
        self.cache.clear()

    def open(self, path):
        self.state.frame_count = 0
        token = self.state.invalidate()
        self._invalidate_reference()

        def work():
            self._close_worker()
            self._reader = self._reader_factory(path)
            reference, error = self._reference_worker()
            return self._reader.metadata, self._reader.timing_summary, reference, error
        self._schedule(token, "open", work)

    def _invalidate_reference(self):
        self._photometric_revision += 1
        self._pending_reference = None
        self.photometric = self.photometric_error = None

    def _reference_worker(self):
        try:
            preset = load_photometric_preset()
            count = self._reader.metadata.frame_count
            index = cine_reference_index(count)
            # An explicit recalculation reads the reference again; navigation never does.
            pixels = self._reader.read_frame(index)
            pixels.setflags(write=False)
            self.cache.put(index, pixels)
            return estimate_reference(pixels, count, preset), None
        except Exception as error:
            return None, str(error)

    def recalculate_reference(self):
        if not self.state.frame_count or self._shutdown:
            return
        self._photometric_revision += 1
        self.photometric = self.photometric_error = None
        self.photometric_changed.emit()
        self._pending_reference = (self._photometric_revision, "reference", self._reference_worker)
        if self._task is None:
            self._start_pending()

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

    @property
    def busy(self):
        return self._task is not None or self._pending is not None

    def cancel_frame_requests(self, displayed_index):
        """Pause invalidates in-flight pixels without interrupting reader I/O."""
        self.state.request(displayed_index)
        if self._pending is not None and self._pending[1] == "frame":
            self._pending = None

    def close(self):
        self.state.frame_count = 0
        self._invalidate_reference()
        self._schedule(self.state.invalidate(), "close", self._close_worker)

    def _schedule(self, token, kind, work):
        if self._shutdown:
            return
        self._pending = (token, kind, work)  # at most one newest request is retained
        if self._task is None:
            self._start_pending()

    def _start_pending(self):
        if self._shutdown:
            return
        if self._pending_reference is not None:
            token, kind, work = self._pending_reference
            self._pending_reference = None
        elif self._pending is not None:
            token, kind, work = self._pending
            self._pending = None
        else:
            return
        self._task = _Task(token, kind, work)
        self._task.signals.done.connect(self._complete)
        self.pool.start(self._task)

    @Slot(int, str, object, object)
    def _complete(self, token, kind, result, error):
        self._task = None
        if not self._shutdown and kind == "reference":
            if token == self._photometric_revision and self.state.frame_count:
                self.photometric, self.photometric_error = result if error is None else (None, error)
                self.photometric_changed.emit()
        elif not self._shutdown and self.state.accepts(token):
            if error is not None:
                self.failed.emit(error)
            elif kind == "open":
                metadata, timing, self.photometric, self.photometric_error = result
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
        self._pending_reference = None
        self.pool.waitForDone()
        self._close_worker()
