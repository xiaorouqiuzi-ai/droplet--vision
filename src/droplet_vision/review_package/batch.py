"""Read-only recursive Cine discovery and sequential annotation-package jobs.

Paths exist only in the runtime plan. The persistent manifest contains portable
relative paths. No Qt, database, Queue, or alternative image encoder is involved.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import tempfile
import time

from .cine_export import export_uniform_cine, inspect_cine
from .bundle import context_frames, portable_json
from ..annotations.schema import _now
from ..annotations.scheme import validate_scheme
from ..sampling.uniform import uniform_frame_indices

POLICIES = ('skip', 'overwrite', 'report_conflict')


class BatchCancelled(Exception):
    pass


class OutputConflict(Exception):
    pass


def _roots(source_root, output_parent):
    source, output = Path(source_root).resolve(), Path(output_parent).resolve()
    if source == Path(source.anchor):
        raise ValueError('Choose a dataset folder, not a drive root.')
    destination = output / source.name
    if output == source or source in output.parents or destination == source or source in destination.parents:
        raise ValueError('Output must be outside the source tree.')
    # Resolve existing links as well as lexical paths, including mirrored folders.
    resolved = destination.resolve()
    if resolved == source or source in resolved.parents or not resolved.is_relative_to(output):
        raise ValueError('Output must be outside the source tree.')
    return source, output


def map_cine_to_package_path(source_root, output_parent, cine_path):
    source, output = _roots(source_root, output_parent)
    relative = Path(cine_path).resolve().relative_to(source)
    return output / source.name / relative.with_suffix('.dvapkg')


def discover_cines(source_root, checkpoint=lambda: None):
    """Deterministic, case-insensitive extension match; never traverse links."""
    root = Path(source_root).resolve()
    if not root.is_dir():
        raise ValueError('Source folder does not exist.')
    paths = []
    def linked(path):
        return path.is_symlink() or (os.name == 'nt' and bool(path.stat().st_file_attributes & 0x400))
    def failed(error):
        raise error
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=failed):
        checkpoint()
        dirs[:] = sorted(d for d in dirs if not linked(Path(directory) / d))
        for name in files:
            path = Path(directory) / name
            if path.suffix.lower() == '.cine' and not linked(path):
                paths.append(path)
    return sorted(paths, key=lambda p: (p.relative_to(root).as_posix().casefold(), p.as_posix()))


@dataclass
class BatchPackageItem:
    relative_source_path: str
    relative_package_path: str
    info: dict | None = None
    status: str = 'READY'
    error_type: str = ''
    error_message: str = ''
    actual_sample_count: int = 0
    frames_decoded: int = 0
    source_unchanged: bool | None = None
    elapsed_seconds: float = 0

    def to_dict(self):
        return {**vars(self), 'info': deepcopy(self.info)}


@dataclass
class BatchPackagePlan:
    source_root: Path
    output_parent: Path
    sample_count: int
    context: int
    existing_policy: str
    scheme: dict
    items: list[BatchPackageItem] = field(default_factory=list)

    @property
    def output_root(self):
        return self.output_parent / self.source_root.name


@dataclass
class BatchPackageResult:
    items: list[BatchPackageItem]
    cancelled: bool
    elapsed_seconds: float

    @property
    def created(self):
        return sum(i.status in ('CREATED', 'shortened_to_all_frames') for i in self.items)

    @property
    def skipped(self):
        return sum(i.status in ('SKIPPED_EXISTING', 'CONFLICT') for i in self.items)

    @property
    def failed(self):
        return sum(i.status == 'FAILED' for i in self.items)

    def manifest(self, plan):
        return dict(schema_version=1, created_at=_now(), source_root_name=plan.source_root.name,
                    requested_sample_count=plan.sample_count, context=plan.context,
                    existing_policy=plan.existing_policy, scheme=deepcopy(plan.scheme),
                    total_cines=len(self.items), created=self.created, skipped=self.skipped,
                    failed=self.failed, cancelled=self.cancelled, elapsed_seconds=self.elapsed_seconds,
                    total_frames_decoded=sum(i.frames_decoded for i in self.items),
                    items=[i.to_dict() for i in self.items])


def _error(item, error, plan):
    item.status, item.error_type = 'FAILED', type(error).__name__
    # OS/decoder diagnostics may include local paths. Never leak them to logs.
    message = str(error)
    for path in (plan.source_root, plan.output_parent):
        message = message.replace(str(path), '<folder>').replace(path.as_posix(), '<folder>')
    item.error_message = re.sub(r'[A-Za-z]:[\\/][^\r\n\'\"]*', '<local path>', message)
    try:
        portable_json(item.error_message)
    except ValueError:
        item.error_message = 'Local filesystem error; inspect the source or output permissions.'


def scan_batch(source_root, output_parent, sample_count, scheme, *, context=0,
               existing_policy='skip', checkpoint=lambda: None, progress=lambda event: None):
    source, output = _roots(source_root, output_parent)
    uniform_frame_indices(1, sample_count)  # Shared validation, no new sampler.
    context_frames([0], 1, context)
    if existing_policy not in POLICIES:
        raise ValueError('Unknown existing-file policy')
    validate_scheme(scheme)
    plan = BatchPackagePlan(source, output, sample_count, context, existing_policy, deepcopy(scheme))
    paths = discover_cines(source, checkpoint)
    destinations = {}
    for index, path in enumerate(paths):
        checkpoint()
        destination = map_cine_to_package_path(source, output, path)
        item = BatchPackageItem(path.relative_to(source).as_posix(), destination.relative_to(output).as_posix())
        plan.items.append(item)
        destinations.setdefault(str(destination).casefold(), []).append(item)
        try:
            item.info = inspect_cine(path)
            item.actual_sample_count = len(uniform_frame_indices(item.info['frame_count'], sample_count))
            item.status = ('EXISTS' if destination.exists() else
                           'SHORT' if item.actual_sample_count < sample_count else 'READY')
            item.source_unchanged = True
        except Exception as error:
            _error(item, error, plan)
            if 'SOURCE CHANGED' in str(error):
                item.source_unchanged = False
        progress(dict(phase='scan', index=index+1, total=len(paths), source=item.relative_source_path))
    for group in destinations.values():
        if len(group) > 1:
            for item in group:
                _error(item, ValueError('Multiple Cine names map to the same package path.'), plan)
    return plan


def _safe_destination(plan, item):
    source, output = _roots(plan.source_root, plan.output_parent)
    destination = map_cine_to_package_path(source, output, source / item.relative_source_path)
    resolved = destination.resolve()
    if not resolved.is_relative_to(plan.output_root.resolve()) or resolved.is_relative_to(source):
        raise ValueError('Output link escapes the output tree.')
    return destination


def _write_manifest(plan, result):
    _roots(plan.source_root, plan.output_parent)
    payload = result.manifest(plan)
    portable_json(payload)
    root = plan.output_root
    root.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.batch-', suffix='.tmp', dir=root)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, root / '_batch_manifest.json')
    finally:
        Path(name).unlink(missing_ok=True)


def execute_batch(plan, *, checkpoint=lambda: None, progress=lambda event: None, version='unknown'):
    """Only one Cine and its selected encoded PNGs are retained at a time."""
    started = time.monotonic()
    items = deepcopy(plan.items)
    cancelled = False
    for position, item in enumerate(items):
        if item.status == 'FAILED':
            continue
        tick = time.monotonic()
        before = None
        path = plan.source_root / item.relative_source_path
        try:
            checkpoint()
            destination = _safe_destination(plan, item)
            before = path.stat()
            if (before.st_size, before.st_mtime_ns) != (item.info['file_size_bytes'], item.info['mtime_ns']):
                item.source_unchanged = False
                raise RuntimeError('SOURCE CHANGED since scan')
            if destination.exists() and plan.existing_policy != 'overwrite':
                item.status = 'SKIPPED_EXISTING' if plan.existing_policy == 'skip' else 'CONFLICT'
                continue
            indices = uniform_frame_indices(item.info['frame_count'], plan.sample_count)
            total = len(context_frames(indices, item.info['frame_count'], plan.context)) + 1
            def decoded(frame):
                item.frames_decoded += 1
                progress(dict(phase='create', index=position, total=len(items), source=item.relative_source_path,
                              decoded=item.frames_decoded, frame_total=total, frame_index=frame))
            def commit_guard():
                checkpoint()
                _safe_destination(plan, item)
                if destination.exists() and plan.existing_policy != 'overwrite':
                    raise OutputConflict('Destination appeared during generation; preserved existing file.')
            export_uniform_cine(path, destination, plan.sample_count, plan.scheme, context=plan.context,
                                allow_short=True, expected=item.info, version=version,
                                checkpoint=checkpoint, progress=decoded, before_commit=commit_guard,
                                batch_metadata=dict(requested_sample_count=plan.sample_count,
                                                    actual_sample_count=len(indices), context_frames=plan.context,
                                                    relative_source_path=item.relative_source_path))
            item.status = 'shortened_to_all_frames' if len(indices) < plan.sample_count else 'CREATED'
        except BatchCancelled:
            item.status = 'CANCELLED'
            cancelled = True
        except OutputConflict:
            item.status = 'SKIPPED_EXISTING' if plan.existing_policy == 'skip' else 'CONFLICT'
        except Exception as error:
            _error(item, error, plan)
        finally:
            if before is not None:
                try:
                    after = path.stat()
                    unchanged = (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
                except OSError:
                    unchanged = False
                item.source_unchanged = item.source_unchanged is not False and unchanged
                if not item.source_unchanged:
                    _error(item, RuntimeError('SOURCE CHANGED; inspect this Cine before retrying.'), plan)
            item.elapsed_seconds = time.monotonic() - tick
            progress(dict(phase='item_done', index=position+1, total=len(items), source=item.relative_source_path,
                          status=item.status))
        if cancelled:
            for remaining in items[position+1:]:
                if remaining.status != 'FAILED':
                    remaining.status = 'NOT_PROCESSED'
            break
    result = BatchPackageResult(items, cancelled, time.monotonic()-started)
    _write_manifest(plan, result)
    return result
