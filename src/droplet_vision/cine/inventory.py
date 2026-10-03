"""Portable per-file inventory; no image decoding, pandas or default hashing."""

from __future__ import annotations

import csv
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

from .reader import CineReader

_logger = logging.getLogger(__name__)
_METADATA_FIELDS = (
    "filename", "file_size_bytes", "frame_count", "width", "height", "bit_depth",
    "pixel_dtype", "compression", "fps_header", "shutter_ns", "post_trigger",
    "frame_delay_ns", "serial", "camera_version", "firmware_version", "software_version",
    "recording_time_zone", "cfa", "d_frame_rate", "f_decimation",
)
_TIMING_FIELDS = (
    "fps_timestamp", "fps_ratio", "timestamp_count", "timestamps_monotonic",
    "duplicate_timestamp_count", "non_monotonic_count", "duration_timestamp_s", "timing_status",
)
_INTERVAL_FIELDS = ("mean", "median", "std", "min", "max")
_INVENTORY_FIELDS = (
    ("relative_path", "readable", "error_type", "error_message") + _METADATA_FIELDS
    + _TIMING_FIELDS + tuple("interval_" + name + "_us" for name in _INTERVAL_FIELDS)
    + ("sha256", "notes", "warnings")
)


def discover_cine_files(root: Union[str, Path], recursive: bool = True) -> List[Path]:
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError("Inventory root must be an existing directory")
    candidates = root.rglob("*") if recursive else root.iterdir()
    return sorted((path for path in candidates if path.is_file() and path.suffix.lower() == ".cine"),
                  key=lambda path: path.relative_to(root).as_posix())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_cine(path: Union[str, Path], root: Optional[Union[str, Path]] = None,
                 strict: bool = False, compute_hash: bool = False,
                 mismatch_threshold: float = 0.01) -> Dict[str, Any]:
    path = Path(path).expanduser().absolute()
    root = Path(root).expanduser().absolute() if root is not None else path.parent
    relative = path.relative_to(root).as_posix()
    row = dict.fromkeys(_INVENTORY_FIELDS)
    row.update(relative_path=relative, filename=path.name, readable=False,
               notes=[], warnings=[])
    try:
        row["file_size_bytes"] = path.stat().st_size
        with CineReader(path, mismatch_threshold=mismatch_threshold) as reader:
            metadata = reader.metadata.to_dict()
            timing = reader.timing_summary.to_dict()
            row.update({name: metadata[name] for name in _METADATA_FIELDS})
            row.update({name: timing[name] for name in _TIMING_FIELDS})
            row["notes"] = metadata["notes"]
            row["warnings"] = timing["warnings"]
            for name in _INTERVAL_FIELDS:
                value = timing["interval_" + name + "_s"]
                row["interval_" + name + "_us"] = None if value is None else value * 1e6
        if compute_hash:
            row["sha256"] = _sha256(path)
        row["readable"] = True
    except Exception as exc:
        if strict:
            raise
        message = str(exc)
        # Backend/OS exceptions may embed the input's absolute path.
        for local in (path, path.resolve(), root):
            for representation in (repr(str(local))[1:-1], str(local), local.as_posix()):
                message = message.replace(representation, relative)
        row.update(error_type=type(exc).__name__, error_message=message)
        _logger.debug("Cannot inspect %s: %s", relative, type(exc).__name__)
    return row


def build_inventory(root: Union[str, Path], recursive: bool = True,
                    strict: bool = False, compute_hash: bool = False,
                    mismatch_threshold: float = 0.01) -> List[Dict[str, Any]]:
    root = Path(root).expanduser().resolve()
    return [inspect_cine(path, root, strict, compute_hash, mismatch_threshold)
            for path in discover_cine_files(root, recursive)]


def _output_path(path: Union[str, Path]) -> Path:
    path = Path(path)
    if path.resolve().suffix.lower() in {".cine", ".chd"}:
        raise ValueError("Refusing to write an output over a Cine/CHD file")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_inventory_csv(rows: Iterable[Dict[str, Any]], path: Union[str, Path]) -> None:
    with _output_path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=_INVENTORY_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, list)
                             else value for key, value in row.items()})


def write_inventory_json(rows: Iterable[Dict[str, Any]], path: Union[str, Path],
                         scan_root: Optional[Union[str, Path]] = None,
                         include_absolute_root: bool = False) -> None:
    document = {"schema_version": "0.1", "records": list(rows)}
    if include_absolute_root:
        if scan_root is None:
            raise ValueError("scan_root is required when include_absolute_root=True")
        document["scan_root"] = str(Path(scan_root).resolve())
    with _output_path(path).open("w", encoding="utf-8") as stream:
        json.dump(document, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
