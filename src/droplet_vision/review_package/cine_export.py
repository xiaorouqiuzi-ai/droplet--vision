"""Local-only Cine adapter for exporting selected raw frames, never used by readers."""
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path

from .bundle import export_package
from ..cine import CineReader
from ..display.photometric import cine_reference_index, estimate_reference, load_photometric_preset
from ..annotations import AnnotationDocument
from ..sampling.uniform import uniform_frame_indices


def export_cines(requests, scheme, context=5, creator='', version='unknown', purpose='review'):
    """Each request holds a local path/document/targets. Paths never enter the bundle."""
    before = {Path(r['path']).resolve(): (Path(r['path']).stat().st_size, Path(r['path']).stat().st_mtime_ns)
              for r in requests}
    try:
        with ExitStack() as stack:
            sources = []
            for request in requests:
                reader = stack.enter_context(CineReader(request['path']))
                doc, meta = request['document'], reader.metadata
                identity = reader.build_frame_result(0).cine_id
                if doc.cine_id != identity or not doc.matches_cine(meta.filename, meta.file_size_bytes, meta.frame_count, meta.width, meta.height):
                    raise ValueError('AnnotationDocument does not match the selected Cine')
                photo = request.get('photometric')
                if photo is None:
                    try:
                        photo = estimate_reference(reader.read_frame(cine_reference_index(meta.frame_count)),
                                                   meta.frame_count, load_photometric_preset()).to_dict()
                    except ValueError:
                        photo = None  # Explicit Raw fallback, never an invented gain.
                sources.append({**request, 'get_frame':reader.read_frame,
                                'get_metadata':reader.build_frame_result, 'photometric':photo})
            return export_package(sources, deepcopy(scheme), context, creator, version, purpose)
    finally:
        for path, expected in before.items():
            after = path.stat()
            if (after.st_size, after.st_mtime_ns) != expected:
                raise RuntimeError('SOURCE CHANGED during read-only export: ' + path.name)


def inspect_cine(path):
    """Read metadata only; retain local stat for the preview/export race check."""
    path = Path(path).resolve()
    before = path.stat()
    try:
        with CineReader(path) as reader:
            meta = reader.metadata
            return {'cine_id': reader.build_frame_result(0).cine_id, 'filename': meta.filename,
                    'file_size_bytes': meta.file_size_bytes, 'mtime_ns': before.st_mtime_ns,
                    'frame_count': meta.frame_count, 'width': meta.width, 'height': meta.height}
    finally:
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise RuntimeError('SOURCE CHANGED during metadata inspection')


def export_uniform_cine(path, destination, sample_count, scheme, *, context=0,
                        purpose='annotation', creator='', version='unknown',
                        allow_short=False, expected=None, document=None):
    """One Cine, bounded sampled reads; retain encoded PNGs, never a whole video.

    A detached raw-only base may merge into a matching Cine document without
    having shared its random document ID. Existing bases keep strict identity.
    """
    path, destination = Path(path).resolve(), Path(destination).resolve()
    if destination == path or path.parent == destination.parent or path.parent in destination.parents:
        raise ValueError('Do not export into the source Cine directory')
    before = path.stat()
    info = inspect_cine(path)
    if expected is not None and info != expected:
        raise ValueError('Cine changed since sampling preview; reopen the dialog')
    indices = uniform_frame_indices(info['frame_count'], sample_count)
    if info['frame_count'] < sample_count and not allow_short:
        raise ValueError('Confirm exporting all frames for a short Cine first')
    standalone = document is None
    if standalone:
        document = AnnotationDocument(info['cine_id'], info['filename'], info['file_size_bytes'],
                                      info['frame_count'], info['width'], info['height'])
        document.scheme = deepcopy(scheme)
    else:
        document = AnnotationDocument.from_dict(document.to_dict())
        if document.scheme and document.scheme != scheme:
            raise ValueError('AnnotationDocument and export scheme snapshots differ')
    try:
        package = export_cines([{'path': path, 'document': document, 'targets': indices,
                                 'standalone_empty_base': standalone}], scheme, context, creator, version, purpose)
        package.manifest['sampling'] = {'method': 'uniform_frame_sampling', 'requested_samples': sample_count,
                                        'actual_target_count': len(indices), 'frame_indices': indices,
                                        'context_radius': context, 'rounding': 'nearest_ties_to_even'}
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise RuntimeError('SOURCE CHANGED during uniform export')
        package.save(destination)
        return package
    finally:
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise RuntimeError('SOURCE CHANGED during uniform export')
