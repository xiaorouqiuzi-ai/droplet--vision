"""Bounded TIME64 tag reading and conservative timing diagnostics."""

from __future__ import annotations

import math
import operator
import statistics
import struct
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

from ..enums import TimingStatus
from .exceptions import CineFormatError

_TIME64_SCALE = 2**32


def _time64(value: int) -> int:
    value = operator.index(value)
    if not 0 <= value < 2**64:
        raise ValueError("TIME64 must be an unsigned 64-bit integer")
    return value


def time64_delta_seconds(t1: int, t0: int) -> float:
    """Subtract integers first. Preserve all low bits, including status bits."""
    return (_time64(t1) - _time64(t0)) / _TIME64_SCALE


def relative_times_seconds(raw_time64_sequence: Iterable[int]) -> List[float]:
    values = iter(raw_time64_sequence)
    first = next(values, None)
    if first is None:
        return []
    first = _time64(first)
    return [0.0] + [time64_delta_seconds(value, first) for value in values]


def frame_intervals_time64(raw_time64_sequence: Iterable[int]) -> List[int]:
    """Return adjacent signed integer differences in TIME64 ticks, not seconds."""
    values = iter(raw_time64_sequence)
    previous = next(values, None)
    if previous is None:
        return []
    previous = _time64(previous)
    result = []
    for value in values:
        value = _time64(value)
        result.append(value - previous)
        previous = value
    return result


def _read_raw_time64(path: Union[str, Path], off_setup: int,
                    setup_length: int, off_image_offsets: int) -> Tuple[int, ...]:
    """Read only tag 1002 using PIMS-provided offsets; validate the tag chain.

    No Phantom SETUP layout is duplicated here. Unknown blocks are skipped.
    A second Time Only block is rejected rather than silently replacing data.
    """
    start = operator.index(off_setup) + operator.index(setup_length)
    end = operator.index(off_image_offsets)
    size = Path(path).stat().st_size
    if off_setup < 0 or setup_length < 0 or not 0 <= start <= end <= size:
        raise CineFormatError("Invalid or truncated tagged-block region")
    found = None
    with Path(path).open("rb") as stream:
        position = start
        while position < end:
            if end - position < 8:
                raise CineFormatError("Truncated tagged-block header")
            stream.seek(position)
            header = stream.read(8)
            if len(header) != 8:
                raise CineFormatError("Truncated tagged-block header")
            block_size, block_type, more_tags = struct.unpack("<IHH", header)
            if block_size < 8:
                raise CineFormatError("Tagged block_size must be at least 8")
            next_position = position + block_size
            if next_position > end:
                raise CineFormatError("Tagged block crosses off_image_offsets")
            if block_type == 1002:
                if found is not None:
                    raise CineFormatError("Multiple Time Only blocks are ambiguous")
                payload_size = block_size - 8
                if payload_size % 8:
                    raise CineFormatError("TIME64 payload is not divisible by 8")
                payload = stream.read(payload_size)
                if len(payload) != payload_size:
                    raise CineFormatError("Truncated TIME64 payload")
                found = tuple(item[0] for item in struct.iter_unpack("<Q", payload))
            # block_size >= 8 guarantees progress; end bounds the iteration count.
            position = next_position
            if not more_tags:
                break
            if position == end:
                raise CineFormatError("Tag chain announces a missing next block")
    return found if found is not None else ()


@dataclass
class TimingSummary:
    timestamp_count: int = 0
    timestamps_monotonic: Optional[bool] = None
    duplicate_timestamp_count: int = 0
    non_monotonic_count: int = 0
    duration_timestamp_s: Optional[float] = None
    interval_mean_s: Optional[float] = None
    interval_median_s: Optional[float] = None
    interval_std_s: Optional[float] = None
    interval_min_s: Optional[float] = None
    interval_max_s: Optional[float] = None
    fps_timestamp: Optional[float] = None
    fps_header: Optional[float] = None
    fps_ratio: Optional[float] = None
    timing_status: TimingStatus = TimingStatus.TIMING_UNKNOWN
    mismatch_threshold: float = 0.01
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["timing_status"] = self.timing_status.value
        return result


def summarize_timing(raw_time64_sequence: Iterable[int],
                     fps_header: Optional[float] = None,
                     expected_frame_count: Optional[int] = None,
                     mismatch_threshold: float = 0.01) -> TimingSummary:
    """Detect mismatch; numeric agreement never establishes validation.

    Relative mismatch is abs(fps_header / fps_timestamp - 1). Interval std is
    population standard deviation. Duplicates count repeated values anywhere;
    non_monotonic_count counts adjacent backwards steps.
    """
    if not math.isfinite(mismatch_threshold) or mismatch_threshold < 0:
        raise ValueError("mismatch_threshold must be finite and nonnegative")
    raw = tuple(_time64(value) for value in raw_time64_sequence)
    summary = TimingSummary(timestamp_count=len(raw), mismatch_threshold=mismatch_threshold)
    if fps_header is not None:
        if math.isfinite(fps_header) and fps_header > 0:
            summary.fps_header = float(fps_header)
        else:
            summary.warnings.append("Header fps is missing or invalid")
    structural_issue = expected_frame_count is not None and len(raw) != expected_frame_count
    if structural_issue:
        summary.warnings.append("Timestamp count differs from frame count; frame mapping is untrusted")
    if len(raw) < 2:
        summary.warnings.append("At least two timestamps are required for timing diagnostics")
        return summary
    ticks = frame_intervals_time64(raw)
    summary.timestamps_monotonic = all(tick > 0 for tick in ticks)
    summary.duplicate_timestamp_count = len(raw) - len(set(raw))
    summary.non_monotonic_count = sum(tick < 0 for tick in ticks)
    intervals = [tick / _TIME64_SCALE for tick in ticks]
    summary.duration_timestamp_s = time64_delta_seconds(raw[-1], raw[0])
    summary.interval_mean_s = statistics.mean(intervals)
    summary.interval_median_s = statistics.median(intervals)
    summary.interval_std_s = statistics.pstdev(intervals)
    summary.interval_min_s = min(intervals)
    summary.interval_max_s = max(intervals)
    if not summary.timestamps_monotonic:
        summary.warnings.append("Duplicate or backwards timestamps; timing is not usable")
        return summary
    if structural_issue:
        return summary
    summary.fps_timestamp = (len(raw) - 1) / summary.duration_timestamp_s
    if summary.fps_header is not None:
        summary.fps_ratio = summary.fps_header / summary.fps_timestamp
        if abs(summary.fps_ratio - 1.0) > mismatch_threshold:
            summary.timing_status = TimingStatus.TIMING_MISMATCH_UNRESOLVED
            summary.warnings.append("Header and timestamp fps mismatch remains unresolved")
    return summary
