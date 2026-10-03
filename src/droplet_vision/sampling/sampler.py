"""Bounded streaming raw-frame probing, local refinement and source protection."""
from __future__ import annotations
from pathlib import Path
import re
import time
import numpy as np
from ..cine import CineReader
from .config import load_sampling_config
from .schema import AnnotationQueueItem, resolve_relative
from .queue import AnnotationQueue


class SourceChangedError(RuntimeError):
    """Sampling must stop if source size/mtime changes or a source disappears."""


def source_signature(path):
    stat = Path(path).stat()
    return stat.st_size, stat.st_mtime_ns


def verify_source(path, before):
    try:
        after = source_signature(path)
    except OSError as error:
        raise SourceChangedError("Source disappeared/unavailable: " + str(path)) from error
    if after != before:
        raise SourceChangedError("Source size/mtime changed: " + str(path))


def outside_source(output, root):
    if Path(output).resolve().is_relative_to(Path(root).resolve()):
        raise ValueError("Output must not be inside the read-only dataset root")


def anchor_indices(frame_count, fractions):
    if frame_count < 1:
        raise ValueError("Empty Cine")
    result = {}
    for fraction in fractions:
        index = max(0, min(frame_count - 1, round((frame_count - 1) * fraction)))
        # Two decimal places for the default preset; retain finer custom fractions.
        label = f"{fraction:.10f}".rstrip("0").rstrip(".")
        label = label + (".00" if "." not in label else "0" if len(label.split(".")[1]) == 1 else "")
        result.setdefault(index, []).append("anchor_" + label)
    return {index: list(dict.fromkeys(reasons)) for index, reasons in result.items()}


def probe_indices(frame_count, maximum):
    if frame_count < 1:
        raise ValueError("Empty Cine")
    return np.unique(np.rint(np.linspace(0, frame_count - 1, min(frame_count, maximum))).astype(np.int64)).tolist()


def change_score(previous, current) -> float:
    if (previous.dtype != np.uint8 or current.dtype != np.uint8 or previous.ndim != 2
            or current.shape != previous.shape or not previous.size):
        raise ValueError("Sampling v1 requires same-shape raw uint8 grayscale frames")
    return float(np.mean(np.abs(current.astype(np.float32) - previous.astype(np.float32)), dtype=np.float32) / 255.0)


def select_intervals(intervals, maximum, separation):
    selected = []
    for row in sorted(intervals, key=lambda r: (-r["score"], r["left"], r["right"])):
        if len(selected) >= maximum:
            break
        # A flat Cine need not supply artificial change peaks.
        if row["score"] <= 0:
            continue
        midpoint = (row["left"] + row["right"]) / 2
        if all(abs(midpoint - (s["left"] + s["right"]) / 2) >= separation for s in selected):
            selected.append(row)
    return selected


def sample_reader(reader, cine_path, config=None):
    """Only two raw frames are retained; scalar score tables may cover all probes.

    The refined peak index is the SECOND frame of the maximum adjacent pair.
    Score ties select the earliest pair. Coarse midpoint and refined-index
    separation both enforce diversity; skipped candidates are not backfilled.
    """
    config = config or load_sampling_config()
    count = reader.metadata.frame_count
    anchors = anchor_indices(count, config.anchor_fractions)
    probes = probe_indices(count, config.max_probe_frames)
    decoded = {"probe_frames": 0, "refinement_frames": 0}

    def read(index, stage):
        decoded[stage] += 1
        frame = np.asarray(reader.read_frame(index))
        if frame.ndim != 2 or frame.dtype != np.uint8 or not frame.size:
            raise ValueError("Sampling v1 requires raw uint8 grayscale frames")
        return frame

    previous = read(probes[0], "probe_frames")
    intervals = []
    for left, right in zip(probes, probes[1:]):
        current = read(right, "probe_frames")
        intervals.append({"left": left, "right": right, "score": change_score(previous, current)})
        previous = current
    del previous
    separation = max(config.minimum_peak_separation_frames, round(count * config.minimum_peak_separation_fraction))
    selected = select_intervals(intervals, config.max_change_peaks, separation)
    peaks = {}
    for row in selected:
        left, right = row["left"], row["right"]
        previous = read(left, "refinement_frames")
        best_score, best_index = -1.0, None
        for index in range(left + 1, right + 1):
            current = read(index, "refinement_frames")
            score = change_score(previous, current)
            if score > best_score:
                best_score, best_index = score, index
            previous = current
        if best_score > 0 and all(abs(best_index - other) >= separation for other in peaks):
            peaks[best_index] = {"change_score": best_score, "coarse_left": left, "coarse_right": right,
                                 "local_peak_previous_frame": best_index - 1, "local_peak_frame": best_index}
    items = []
    for index in sorted(set(anchors) | set(peaks)):
        frame = reader.build_frame_result(index)
        reasons = anchors.get(index, []) + (["change_peak"] if index in peaks else [])
        items.append(AnnotationQueueItem(
            relative_cine_path=cine_path, cine_id=frame.cine_id, cine_filename=Path(cine_path).name,
            frame_index=index, frame_count=count, frame_fraction=index / (count-1) if count > 1 else 0.0,
            raw_time64=frame.timestamp_time64, relative_timestamp_s=frame.timestamp_s,
            timing_status=frame.timing_status.value, sample_reasons=reasons,
            priority=max(config.anchor_priority if index in anchors else 0,
                         config.change_peak_priority if index in peaks else 0), **peaks.get(index, {})))
    report = {"relative_path": cine_path, "frame_count": count, "queue_item_count": len(items),
              **decoded, "total_decoded": sum(decoded.values()), "peak_separation_frames": separation,
              "selected_coarse_intervals": selected, "refined_peak_count": len(peaks),
              "frame_fraction_min": min(i.frame_fraction for i in items) if items else None,
              "frame_fraction_max": max(i.frame_fraction for i in items) if items else None}
    return items, report


def build_annotation_queue(root, config=None, recursive=True, reader_factory=CineReader, progress=None):
    root = Path(root).resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)
    config = config or load_sampling_config()
    paths = sorted((p for p in (root.rglob("*") if recursive else root.iterdir())
                    if p.is_file() and p.suffix.lower() == ".cine"), key=lambda p: p.relative_to(root).as_posix())
    # Validate symlink containment and capture every signature BEFORE any decoding.
    baseline = {}
    for path in paths:
        resolve_relative(root, path.relative_to(root).as_posix())
        baseline[path] = source_signature(path)
    queue = AnnotationQueue(root.name + " sampling v1", config.preset_id, root.name,
                            sampling_config={**config.to_dict(), "config_sha256": config.sha256, "sampler_version": 1,
                                             "numpy_version": np.__version__})
    for path in paths:
        relative = path.relative_to(root).as_posix()
        start = time.perf_counter()
        try:
            verify_source(path, baseline[path])
            with reader_factory(path) as reader:
                items, report = sample_reader(reader, relative, config)
            for item in items:
                item.cine_file_size, item.cine_mtime_ns = baseline[path]
            queue.items.extend(items)
            report.update(source_file_size=baseline[path][0], source_mtime_ns=baseline[path][1],
                          source_unchanged=True, elapsed_seconds=time.perf_counter() - start)
            queue.sampling_report.append(report)
        except SourceChangedError:
            raise
        except Exception as error:
            message = str(error).replace(str(root), "<dataset_root>").replace(root.as_posix(), "<dataset_root>")
            message = re.sub(r"[A-Za-z]:[\\/][^\r\n'\"]*", "<local_path>", message)
            queue.failed_files.append({"relative_path": relative, "error_type": type(error).__name__, "error_message": message})
        finally:
            verify_source(path, baseline[path])
        if progress is not None:
            progress(relative)
    for path, signature in baseline.items():
        verify_source(path, signature)
    return queue


def summarize_queue(queue):
    scores = [i.change_score for i in queue.items if i.change_score is not None]
    return {"cine_count": len(queue.sampling_report) + len(queue.failed_files),
            "failed_cine_count": len(queue.failed_files), "total_queue_items": len(queue.items),
            "items_per_cine": queue.sampling_report,
            "anchor_count": sum(any(r.startswith("anchor_") for r in i.sample_reasons) for i in queue.items),
            "change_peak_count": sum("change_peak" in i.sample_reasons for i in queue.items),
            "merged_anchor_change_count": sum("change_peak" in i.sample_reasons and len(i.sample_reasons) > 1 for i in queue.items),
            "change_score_distribution": dict(zip(("min", "p05", "median", "p95", "max"),
                                                  map(float, np.percentile(scores, [0, 5, 50, 95, 100])))) if scores else None,
            "source_unchanged": True, "sampling_pixels": "raw uint8", "physical_event_labels": False}
