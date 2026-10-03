"""Read-only PIMS 0.7 adapter, with lazy pixels and bounded tag parsing."""

from __future__ import annotations

import logging
import operator
from pathlib import Path
from typing import Any, Iterable, Iterator, Tuple, Union

from ..schema import FrameResult
from .exceptions import CineDependencyError, CineFormatError
from .metadata import _extract_metadata
from .timing import _read_raw_time64, summarize_timing, time64_delta_seconds

_logger = logging.getLogger(__name__)


def _open_backend(path: Path) -> Any:
    try:
        from pims import Cine
    except ImportError as exc:
        raise CineDependencyError(
            "Cine support requires the optional 'cine' dependencies (PIMS 0.7). "
            "Use an environment with those dependencies; no installation is performed."
        ) from exc

    class _BoundedCine(Cine):
        def _read_tagged_blocks(self):
            # PIMS calls this after parsing headers but before its unbounded
            # tagged-block loop. Validate the complete chain before delegating.
            self._raw_time64 = _read_raw_time64(
                path, self.off_setup, self.setup_length, self.off_image_offsets)
            if self.off_image_offsets + self.image_count * 8 > path.stat().st_size:
                raise CineFormatError("Truncated image offset table")
            tags = super()._read_tagged_blocks() or {}
            tags.setdefault("image_time_only", [])
            tags.setdefault("exposure_only", [])
            return tags

    # Keep the partially initialized object reachable for deterministic cleanup.
    backend = _BoundedCine.__new__(_BoundedCine)
    try:
        backend.__init__(str(path))
    except BaseException:
        if hasattr(backend, "f"):
            backend.f.close()
        raise
    return backend


class CineReader:
    """Read PIMS-decoded pixels unchanged; no preprocessing or image export.

    frame_shape follows array order (height, width[, channels]), correcting
    PIMS 0.7's width/height metadata order. Opening reads headers/index/tags,
    never image pixels. Callers should use a context manager or close().
    """

    def __init__(self, path: Union[str, Path], mismatch_threshold: float = 0.01):
        self.path = Path(path).expanduser().resolve()
        self._backend = None
        if not self.path.exists():
            raise FileNotFoundError("Cine file does not exist: " + str(self.path))
        if not self.path.is_file():
            raise IsADirectoryError("Cine path is not a file: " + str(self.path))
        try:
            self._backend = _open_backend(self.path)
            self.raw_time64: Tuple[int, ...] = self._backend._raw_time64
            self.metadata = _extract_metadata(self.path, self._backend, len(self.raw_time64))
            self.frame_count = len(self._backend)
            self.frame_shape = (self.metadata.height, self.metadata.width)
            if self.metadata.cfa != 0:
                self.frame_shape += (3,)
            self.pixel_dtype = self._backend.pixel_type
            self.frame_rate_header = self.metadata.fps_header
            self.compression = self.metadata.compression
            self.timing_summary = summarize_timing(
                self.raw_time64, self.frame_rate_header, self.frame_count, mismatch_threshold)
        except BaseException:
            self.close()
            raise
        _logger.debug("Opened Cine headers for %s (%d frames)", self.path.name, self.frame_count)

    @property
    def closed(self) -> bool:
        return self._backend is None

    def _ensure_open(self) -> None:
        if self.closed:
            raise ValueError("CineReader is closed")

    def _index(self, index: int) -> int:
        self._ensure_open()
        if isinstance(index, bool):
            raise TypeError("Frame index must be an integer, not bool")
        index = operator.index(index)
        if not 0 <= index < self.frame_count:
            raise IndexError("Frame index {} outside [0, {})".format(index, self.frame_count))
        return index

    def __len__(self) -> int:
        return self.frame_count

    def read_frame(self, index: int, copy: bool = True) -> Any:
        """Return one ndarray; default storage is independent of the backend.

        PIMS's private pixel decoder avoids get_frame's required timestamp and
        exposure tags. This narrow PIMS 0.7 adapter is covered by integration
        tests. copy=False makes no ownership/writeability guarantee.
        """
        index = self._index(index)
        import numpy as np

        pixels = np.asarray(self._backend._get_frame(index))
        return pixels.copy() if copy else pixels

    def read_frames(self, indices: Iterable[int]) -> Iterator[Any]:
        """Yield one copied frame at a time, preserving input order/duplicates."""
        self._ensure_open()
        for index in indices:
            yield self.read_frame(index)

    def build_frame_result(self, index: int) -> FrameResult:
        index = self._index(index)
        # A count mismatch cannot establish which timestamp belongs to a frame.
        raw = self.raw_time64[index] if len(self.raw_time64) == self.frame_count else None
        elapsed = None
        if raw is not None and self.timing_summary.timestamps_monotonic:
            elapsed = time64_delta_seconds(raw, self.raw_time64[0])
        timing = self.timing_summary
        return FrameResult(
            cine_id=self.path.stem, frame_index=index, timestamp_s=elapsed,
            timestamp_time64=raw, fps_header=timing.fps_header,
            fps_timestamp=timing.fps_timestamp, fps_ratio=timing.fps_ratio,
            timing_status=timing.timing_status,
            metadata={"filename": self.path.name, "frame_shape": list(self.frame_shape),
                      "pixel_dtype": str(self.pixel_dtype), "timestamp_origin": "first_frame",
                      "timing_warnings": list(timing.warnings),
                      "cine_id_policy": "filename stem; caller must disambiguate duplicate names"},
        )

    def close(self) -> None:
        backend, self._backend = self._backend, None
        if backend is not None:
            backend.close()

    def __enter__(self) -> CineReader:
        self._ensure_open()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()
