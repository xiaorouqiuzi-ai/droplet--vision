"""Local-only Cine adapter for exporting selected raw frames, never used by readers."""
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path

from .bundle import export_package
from ..cine import CineReader
from ..display.photometric import cine_reference_index, estimate_reference, load_photometric_preset


def export_cines(requests, scheme, context=5, creator='', version='unknown'):
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
            return export_package(sources, deepcopy(scheme), context, creator, version)
    finally:
        for path, expected in before.items():
            after = path.stat()
            if (after.st_size, after.st_mtime_ns) != expected:
                raise RuntimeError('SOURCE CHANGED during read-only export: ' + path.name)
