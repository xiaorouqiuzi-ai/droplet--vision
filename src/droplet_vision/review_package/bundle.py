"""Versioned, checksummed raw PNG transport; no Qt and no Cine dependency."""
from __future__ import annotations

from copy import deepcopy
from io import BytesIO
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
from uuid import uuid4
import zipfile

import numpy as np
from PIL import Image

from ..annotations import AnnotationDocument
from ..annotations.schema import _now
from ..annotations.scheme import validate_scheme
from ..display.photometric import PhotometricReference


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_name(name):
    """ZIP names are canonical POSIX relative paths, never native paths."""
    if (not isinstance(name, str) or not name or '\\' in name or ':' in name
            or '\x00' in name or PurePosixPath(name).is_absolute()
            or any(p in ('', '.', '..') for p in name.split('/'))):
        raise ValueError('Unsafe review package path: ' + str(name))
    return name


def portable_json(value):
    """Reject accidental local path disclosure, including free-text provenance."""
    if isinstance(value, dict):
        for item in value.values():
            portable_json(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            portable_json(item)
    elif isinstance(value, str):
        if (re.search(r'[A-Za-z]:[\\/]', value) or value.startswith(('\\\\', '/'))):
            raise ValueError('Package metadata contains an absolute path; remove it before export')


def context_frames(targets, count, context=5):
    if type(context) is not int or not 0 <= context <= 100 or count < 1:
        raise ValueError('Context must be 0–100 frames')
    targets = set(targets)
    if not targets or any(type(i) is not int or not 0 <= i < count for i in targets):
        raise ValueError('Invalid or empty review target selection')
    return {i: ('target' if i in targets else 'context') for t in sorted(targets)
            for i in range(max(0, t-context), min(count, t+context+1))}


def snapshot(document, frames):
    """Active human view plus ancestry; exclude unrelated frames/model-only output."""
    value = document.to_dict()
    records = {r['annotation_id']: r for r in value['records']}
    active = {r.annotation_id for r in document.active_records()
              if r.frame_index in frames and document.record_layers[r.annotation_id] in ('manual', 'reviewed', 'ground_truth')
              and r.annotation_id not in document.support_suppressed_ids(r.frame_index)
              and (r.source != 'model' or r.review_status in ('accepted', 'edited', 'ground_truth'))}
    keep = set(active)
    for key in list(active):
        parent = records[key]['derived_from']
        while parent:
            keep.add(parent)
            parent = records[parent]['derived_from']
    value['records'] = [r for r in value['records'] if r['annotation_id'] in keep]
    value['active_annotation_ids'] = sorted(active)
    value['deactivated_annotation_ids'] = sorted(keep-active)
    value['record_layers'] = {k:v for k,v in value['record_layers'].items() if k in keep}
    # Copies carry their own raw geometry/provenance. Do not expand a sparse
    # package merely to satisfy a template pointer outside its selected frames.
    templates = {k:v for k,v in value.get('cine_templates', {}).items()
                 if set(v['annotation_ids']) <= keep}
    for template in templates.values():
        if 'frame_overrides' in template:
            template['frame_overrides'] = {k:v for k,v in template['frame_overrides'].items() if int(k) in frames}
    if templates:
        value['cine_templates'] = templates
    else:
        value.pop('cine_templates', None)
    states = {r['record_id']:r for r in value['frame_state_records']}
    active_states = {k:v for k,v in value['active_frame_state_records'].items()
                     if int(k) in frames and (states[v]['source'] == 'manual'
                     or states[v]['review_status'] in ('accepted', 'edited', 'ground_truth'))}
    keep_states = set(active_states.values())
    for key in list(keep_states):
        parent = states[key]['derived_from']
        while parent:
            keep_states.add(parent)
            parent = states[parent]['derived_from']
    value['frame_state_records'] = [r for r in value['frame_state_records'] if r['record_id'] in keep_states]
    value['active_frame_state_records'] = active_states
    value['history'] = []  # Record ancestry is retained; unrelated run logs are not exported.
    result = AnnotationDocument.from_dict(value)
    # Materialize only selected package frames. Never change the canonical
    # document or force the template's source frame into a sparse package.
    for frame in sorted(frames):
        for projection in document.support_projections(frame, package=True):
            result.add_record(projection, 'manual')
    return result


class ReviewPackage:
    """In-memory small-frame bundle. ZIP is never extracted into the filesystem."""
    def __init__(self, manifest, scheme, documents, bases, frames, review=None):
        self.manifest, self.scheme = manifest, scheme
        self.documents, self.bases, self.frames = documents, bases, frames
        self.review = review or {'decisions': [], 'frame_notes': {}, 'reviewed_frames': [], 'record_provenance': {}}
        for cine, document in documents.items():
            document.bind_package_scope(row['frame_index'] for row in manifest['frames'] if row['cine_id'] == cine)
        self.path = None
        self.saved_fingerprint = None

    @property
    def dirty(self):
        return self.saved_fingerprint != self.fingerprint()

    def fingerprint(self):
        return digest(encode([self.work_fingerprint(), self.review.get('review_completed_at')]))

    def work_fingerprint(self):
        """Effective work, excluding Undo's retained inactive history/audit entries.

        History remains serialized in full on Save. Display state is not package
        data. Automatically generated review lifecycle fields are not user edits.
        Explicit decisions, notes and reviewed-frame progress are user edits.
        """
        docs, active_ids = {}, set()
        for cine, document in self.documents.items():
            value = document.to_dict()
            objects = set(value['active_annotation_ids'])
            states = set(value['active_frame_state_records'].values())
            active_ids.update(objects | states)
            value['records'] = sorted((r for r in value['records'] if r['annotation_id'] in objects),
                                      key=lambda r: r['annotation_id'])
            value['frame_state_records'] = sorted((r for r in value['frame_state_records'] if r['record_id'] in states),
                                                  key=lambda r: r['record_id'])
            value['record_layers'] = {k:v for k,v in value['record_layers'].items() if k in objects}
            for key in ('deactivated_annotation_ids', 'history', 'updated_at'):
                value.pop(key, None)
            docs[cine] = value
        manifest = {k:v for k,v in self.manifest.items() if k not in ('package_status', 'reviewed_with_app_version')}
        review = {k:v for k,v in self.review.items() if k not in (
            'reviewer', 'review_started_at', 'application_version_reviewed', 'review_completed_at', 'record_provenance')}
        active_ids.update(d['record_id'] for d in self.review['decisions'])
        review['record_provenance'] = {k:v for k,v in self.review.get('record_provenance', {}).items() if k in active_ids}
        return digest(encode([manifest, self.scheme, review, docs]))

    def start_review(self, reviewer='', version='unknown'):
        self.review['reviewer'] = {'display_name': reviewer}
        self.review.setdefault('review_started_at', _now())
        self.review['application_version_reviewed'] = version
        self.manifest['reviewed_with_app_version'] = version
        self.manifest['package_status'] = 'in_review'

    def provenance(self):
        return {'review_origin': 'review_package', 'package_id': self.manifest['package_id'],
                'reviewer': self.review.get('reviewer', {}).get('display_name', ''),
                'package_kind': self.manifest.get('package_kind', 'review_package'),
                'package_purpose': self.manifest.get('package_purpose', 'review')}

    def mark_in_review(self):
        self.manifest['package_status'] = 'in_review'
        self.review.pop('review_completed_at', None)

    def files(self):
        result = {'manifest.json': encode(self.manifest),
                  'scheme/annotation_scheme.json': encode(self.scheme),
                  'scheme/object_taxonomy.json': encode(self.scheme['objects']),
                  'scheme/frame_state_schema.json': encode(self.scheme['frame_states']),
                  'review/review_state.json': encode(self.review), **self.frames}
        for cine, doc in self.documents.items():
            name = self.manifest['base_annotation_documents'][cine]['snapshot_path']
            result[name] = encode({'base': self.bases[cine].to_dict(), 'document': doc.to_dict()})
        for name, content in result.items():
            safe_name(name)
            if name.endswith('.json'):
                portable_json(json.loads(content))
        result['checksums/sha256.json'] = encode({name:digest(data) for name,data in result.items()})
        return result

    def save(self, path, folder=False, mark_saved=True, *, checkpoint=None, before_commit=None):
        """Verify a staged container before replacement; preserve old file on failure."""
        path = Path(path).resolve()
        if not folder and path.suffix.lower() not in ('.dvapkg', '.dvrpkg'):
            raise ValueError('Use the .dvapkg extension (.dvrpkg is also supported)')
        if folder and path.exists():
            raise FileExistsError('Folder export requires a new, empty destination name')
        check = checkpoint or (lambda: None)
        check()
        payload = self.files()
        saved_fingerprint = self.fingerprint() if mark_saved else None
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix='.review-', dir=path.parent))
        try:
            staged = temporary / ('package' if folder else 'package.dvrpkg')
            if folder:
                staged.mkdir()
                for name, data in payload.items():
                    check()
                    target = staged / safe_name(name)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open('xb') as handle:
                        handle.write(data)
                        handle.flush()
                        os.fsync(handle.fileno())
            else:
                with staged.open('xb') as handle:
                    with zipfile.ZipFile(handle, 'w', zipfile.ZIP_DEFLATED) as archive:
                        for name, data in payload.items():
                            check()
                            archive.writestr(name, data)
                    handle.flush()
                    os.fsync(handle.fileno())
            self._from_files(payload)  # Also validate in-memory state before saving.
            self.open(staged)
            check()
            if before_commit is not None:
                before_commit()
            os.replace(staged, path)
        finally:
            # Only the task-owned temporary directory created above is removed.
            # Once replace succeeded, cleanup must not turn a successful save
            # into a reported failure. Temporary residue can be cleaned later.
            shutil.rmtree(temporary, ignore_errors=True)
        if mark_saved:
            self.path = path
            for document in self.documents.values():
                document._saved_revision = document._revision
            self.saved_fingerprint = saved_fingerprint

    @classmethod
    def open(cls, path):
        path = Path(path)
        files = {}
        limit = 1024 * 1024 * 1024  # v1 small review transport, maximum expanded size 1 GiB.
        total = 0
        if path.is_dir():
            if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
                raise ValueError('Symlink package root is not supported')
            for entry in path.rglob('*'):
                if entry.is_symlink() or getattr(entry, 'is_junction', lambda: False)():
                    raise ValueError('Package links are not allowed')
                if entry.is_file():
                    name = safe_name(entry.relative_to(path).as_posix())
                    total += entry.stat().st_size
                    if total > limit:
                        raise ValueError('Expanded package exceeds 1 GiB')
                    files[name] = entry.read_bytes()
        else:
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                if len(entries) > 20000:
                    raise ValueError('Too many package members')
                folded = set()
                for entry in entries:
                    name = safe_name(entry.filename)
                    if name.casefold() in folded or stat.S_ISLNK(entry.external_attr >> 16):
                        raise ValueError('Duplicate member or symlink in package')
                    folded.add(name.casefold())
                    total += entry.file_size
                    if total > limit or entry.file_size > 128*1024*1024:
                        raise ValueError('Package member/expanded size exceeds review limits')
                    files[name] = archive.read(entry)
        result = cls._from_files(files)
        result.path = path
        result.saved_fingerprint = result.fingerprint()
        return result

    @classmethod
    def _from_files(cls, files):
        required = {'manifest.json', 'scheme/annotation_scheme.json', 'scheme/object_taxonomy.json',
                    'scheme/frame_state_schema.json', 'review/review_state.json', 'checksums/sha256.json'}
        if not required <= files.keys():
            raise ValueError('Missing required review package files')
        hashes = json.loads(files['checksums/sha256.json'])
        if set(hashes) != set(files)-{'checksums/sha256.json'}:
            raise ValueError('Checksum inventory differs from package members')
        for name, expected in hashes.items():
            safe_name(name)
            if digest(files[name]) != expected:
                raise ValueError('Package corruption: SHA-256 mismatch for ' + name)
        for name, data in files.items():
            if name.endswith('.json'):
                portable_json(json.loads(data))
        manifest = json.loads(files['manifest.json'])
        if manifest.get('schema_version') != 1 or manifest.get('package_format_version') not in (1, 2):
            raise ValueError('Unsupported annotation package version')
        if manifest['package_format_version'] == 2:
            if (manifest.get('package_kind') != 'annotation_package'
                    or manifest.get('package_purpose') not in ('annotation', 'review', 'general')):
                raise ValueError('Invalid annotation package kind/purpose')
        elif manifest.get('package_kind', 'review_package') != 'review_package':
            raise ValueError('Invalid legacy package kind')
        if manifest.get('package_status') not in ('exported', 'in_review', 'reviewed'):
            raise ValueError('Invalid package status')
        scheme = validate_scheme(json.loads(files['scheme/annotation_scheme.json']))
        if (scheme['objects'] != json.loads(files['scheme/object_taxonomy.json'])
                or scheme['frame_states'] != json.loads(files['scheme/frame_state_schema.json'])
                or manifest['annotation_scheme'] != {k:scheme[k] for k in ('scheme_id', 'version')}):
            raise ValueError('Inconsistent scheme snapshots')
        docs, bases, images, seen = {}, {}, {}, set()
        for cine, meta in manifest['base_annotation_documents'].items():
            container = json.loads(files[safe_name(meta['snapshot_path'])])
            base = AnnotationDocument.from_dict(container['base'])
            doc = AnnotationDocument.from_dict(container['document'])
            if (doc.cine_id != cine or base.cine_id != cine or doc.document_id != base.document_id
                    or base.document_id != meta['document_id'] or digest(encode(base.to_dict())) != meta['snapshot_sha256']):
                raise ValueError('Base document identity/hash mismatch')
            if (meta['base_active_ids'] != sorted(base.active_annotation_ids)
                    or meta['base_active_state_ids'] != base.to_dict()['active_frame_state_records']):
                raise ValueError('Base active record inventory mismatch')
            for row in base.records.records():
                if doc.records.get(row.annotation_id).to_dict() != row.to_dict():
                    raise ValueError('Original snapshot record was overwritten')
            state_rows = {r.record_id:r.to_dict() for r in doc.frame_state_records}
            if any(state_rows.get(r.record_id) != r.to_dict() for r in base.frame_state_records):
                raise ValueError('Original frame-state snapshot was overwritten')
            if doc.to_dict()['cine'] != base.to_dict()['cine'] or doc.scheme != base.scheme:
                raise ValueError('Review cannot change Cine identity or scheme snapshot')
            if doc.cine_templates != base.cine_templates:
                raise ValueError('Review cannot change Cine templates')
            docs[cine], bases[cine] = doc, base
            if type(meta.get('standalone_empty_base', False)) is not bool:
                raise ValueError('Invalid standalone base flag')
            if meta.get('standalone_empty_base', False) and (
                    manifest['package_format_version'] != 2 or base.records.records()
                    or base.frame_state_records or base.cine_templates):
                raise ValueError('Standalone base must be empty')
            base_ids = {r.annotation_id for r in base.records.records()}
            if any(r.source != 'manual' or r.review_status == 'ground_truth'
                   for r in doc.records.records() if r.annotation_id not in base_ids):
                raise ValueError('New reviewer records must be manual, not automatic Ground Truth')
            base_state_ids = {r.record_id for r in base.frame_state_records}
            if any(r.source != 'manual' or r.review_status == 'ground_truth'
                   for r in doc.frame_state_records if r.record_id not in base_state_ids):
                raise ValueError('New reviewer states must be manual review candidates')
        for frame in manifest['frames']:
            cine, index = frame['cine_id'], frame['frame_index']
            if (cine, index) in seen or cine not in docs:
                raise ValueError('Duplicate frame or unknown Cine')
            seen.add((cine,index))
            doc = docs[cine]
            if (type(index) is not int or not 0 <= index < doc.frame_count or frame['frame_count'] != doc.frame_count
                    or frame['role'] not in ('target', 'context') or frame['review_target'] != (frame['role'] == 'target')
                    or frame['cine_filename'] != doc.cine_filename or frame['width'] != doc.width or frame['height'] != doc.height
                    or frame['dtype'] != 'uint8'):
                raise ValueError('Invalid packaged frame metadata')
            from ..schema import TimingStatus
            TimingStatus(frame['timing_status'])
            if frame['raw_time64'] is not None and (type(frame['raw_time64']) is not int or not 0 <= frame['raw_time64'] < 2**64):
                raise ValueError('Invalid TIME64')
            if frame['relative_timestamp_s'] is not None and not math.isfinite(frame['relative_timestamp_s']):
                raise ValueError('Invalid timestamp')
            name = safe_name(frame['raw_png_relative_path'])
            if name in images:
                raise ValueError('Multiple frames reference the same PNG member')
            data = files[name]
            if digest(data) != frame['sha256']:
                raise ValueError('Raw PNG checksum mismatch')
            with Image.open(BytesIO(data)) as image:
                if image.format != 'PNG' or image.mode != 'L' or image.size != (doc.width, doc.height):
                    raise ValueError('Expected raw uint8 grayscale PNG')
                image.load()
            images[name] = data
        for cine, doc in docs.items():
            indices = {index for cid,index in seen if cid == cine}
            doc.bind_package_scope(indices)
            bases[cine].bind_package_scope(indices)
            if not indices or any(r.frame_index not in indices for r in doc.records.records()) or any(r.frame_index not in indices for r in doc.frame_state_records):
                raise ValueError('Annotation refers to an unbundled frame')
        if 'sampling' in manifest:
            from ..sampling.uniform import uniform_frame_indices
            sampling = manifest['sampling']
            if len(docs) != 1 or sampling.get('method') != 'uniform_frame_sampling':
                raise ValueError('Invalid uniform sampling metadata')
            doc = next(iter(docs.values()))
            expected_indices = uniform_frame_indices(doc.frame_count, sampling['requested_samples'])
            targets = sorted(r['frame_index'] for r in manifest['frames'] if r['review_target'])
            if (sampling['frame_indices'] != expected_indices or targets != expected_indices
                    or sampling['actual_target_count'] != len(expected_indices)
                    or sampling.get('rounding') != 'nearest_ties_to_even'):
                raise ValueError('Uniform target inventory mismatch')
            roles = context_frames(expected_indices, doc.frame_count, sampling['context_radius'])
            if {r['frame_index']: r['role'] for r in manifest['frames']} != roles:
                raise ValueError('Uniform context inventory mismatch')
        if (not docs or sorted(manifest['source_cines'], key=lambda r:r['cine_id']) !=
                sorted([d.to_dict()['cine'] for d in bases.values()], key=lambda r:r['cine_id'])):
            raise ValueError('Source Cine inventory mismatch')
        expected = required | set(images) | {v['snapshot_path'] for v in manifest['base_annotation_documents'].values()}
        if set(files) != expected:
            raise ValueError('Unexpected package members (Cine and extra payloads are prohibited)')
        if set(manifest.get('photometric', {})) != set(docs):
            raise ValueError('Photometric Cine inventory mismatch')
        for ref in manifest['photometric'].values():
            if ref is not None:
                reference = PhotometricReference(**ref)
                if not math.isfinite(reference.gain_used) or reference.gain_used <= 0:
                    raise ValueError('Invalid locked display gain')
        review = json.loads(files['review/review_state.json'])
        for cine, index in review['reviewed_frames']:
            if (cine, index) not in seen:
                raise ValueError('Reviewed frame is not in the package')
        frame_keys = {cine + ':' + str(index) for cine,index in seen}
        if any(k not in frame_keys or not isinstance(v, str) for k,v in review['frame_notes'].items()):
            raise ValueError('Invalid review note frame reference')
        for decision in review['decisions']:
            if (decision['cine_id'], decision['frame_index']) not in seen or decision['status'] not in ('accepted', 'rejected', 'needs_review'):
                raise ValueError('Invalid review decision')
            doc = docs[decision['cine_id']]
            rows = ({r.annotation_id:r for r in doc.records.records()} if decision['kind'] == 'object'
                    else {r.record_id:r for r in doc.frame_state_records} if decision['kind'] == 'state' else {})
            row = rows.get(decision['record_id'])
            if row is None or row.derived_from != decision['derived_from'] or row.frame_index != decision['frame_index']:
                raise ValueError('Review decision record mismatch')
        return cls(manifest, scheme, docs, bases, images, review)

    def summary(self):
        targets = sum(f['review_target'] for f in self.manifest['frames'])
        return {'cine_count':len(self.documents), 'target_frames':targets,
                'context_frames':len(self.manifest['frames'])-targets, 'raw_png_count':len(self.frames),
                'annotations':sum(len(d.active_annotation_ids) for d in self.documents.values()),
                'frame_states':sum(len(d.active_frame_state_records) for d in self.documents.values())}

    def progress(self, cine_id):
        """Viewing alone never completes a target; explicit review also counts."""
        doc = self.documents[cine_id]
        targets = {r['frame_index'] for r in self.manifest['frames']
                   if r['cine_id'] == cine_id and r['review_target']}
        done = {r.frame_index for r in doc.active_records()
                if r.source == 'manual' or r.review_status in ('accepted', 'edited', 'ground_truth')}
        done.update(r.frame_index for r in doc.frame_state_records
                    if r.record_id in doc.active_frame_state_records.values()
                    and (r.source == 'manual' or r.review_status in ('accepted', 'edited', 'ground_truth')))
        done.update(index for cine, index in self.review['reviewed_frames'] if cine == cine_id)
        done.update(int(frame) for frame in doc.package_templates.get('support_structure', {}).get('frame_overrides', {}))
        return len(targets), len(targets & done), len(targets - done)


def export_package(sources, scheme, context=5, creator='', version='unknown', purpose='review'):
    """Sources contain document, targets, get_frame(index), get_metadata(index), photometric.

    The caller owns each read-only source lifecycle. Only requested raw frames are read.
    """
    scheme = validate_scheme(scheme)
    if purpose not in ('annotation', 'review', 'general'):
        raise ValueError('Invalid package purpose')
    manifest = {'schema_version':1, 'package_format_version':2, 'package_kind':'annotation_package',
                'package_purpose':purpose, 'package_id':str(uuid4()),
                'created_at':_now(), 'creator':creator, 'application_version':version,
                'created_with_app_version':version, 'reviewed_with_app_version':None,
                'annotation_scheme':{k:scheme[k] for k in ('scheme_id','version')},
                'package_status':'exported', 'source_cines':[], 'frames':[],
                'base_annotation_documents':{}, 'photometric':{}}
    docs, bases, images = {}, {}, {}
    for source in sources:
        original = source['document']
        cine = original.cine_id
        if cine in docs:
            raise ValueError('Group targets for each Cine before exporting')
        selection = context_frames(source['targets'], original.frame_count, context)
        base = snapshot(original, selection)
        base.scheme = deepcopy(scheme)
        base._saved_revision = base._revision
        bases[cine], docs[cine] = base, AnnotationDocument.from_dict(base.to_dict())
        logical = digest(cine.encode())[:24]
        manifest['source_cines'].append(original.to_dict()['cine'])
        manifest['base_annotation_documents'][cine] = {
            'document_id': original.document_id, 'document_sha256':digest(encode(original.to_dict())),
            'snapshot_sha256':digest(encode(base.to_dict())), 'base_active_ids':sorted(base.active_annotation_ids),
            'base_active_state_ids':base.to_dict()['active_frame_state_records'],
            'snapshot_path':f'annotations/{logical}.review_annotations.json'}
        if (source.get('standalone_empty_base') or
                (not original.records.records() and not original.frame_state_records and not original.cine_templates)):
            manifest['base_annotation_documents'][cine]['standalone_empty_base'] = True
        manifest['photometric'][cine] = source.get('photometric')
        for index, role in sorted(selection.items()):
            image = source['get_frame'](index)
            if image.dtype != np.uint8 or image.ndim != 2 or image.shape != (original.height, original.width):
                raise ValueError('Review v1 exports uint8 grayscale raw frames only')
            stream = BytesIO()
            Image.fromarray(image).save(stream, format='PNG')
            data = stream.getvalue()
            if not np.array_equal(image, np.array(Image.open(BytesIO(data)))):
                raise ValueError('Raw PNG pixel equality failed')
            name = f'frames/{logical}/frame_{index:06d}.png'
            images[name] = data
            timing = source['get_metadata'](index)
            manifest['frames'].append({
                'cine_id':cine, 'cine_filename':original.cine_filename,
                'frame_index':index, 'frame_count':original.frame_count,
                'raw_time64':timing.timestamp_time64, 'relative_timestamp_s':timing.timestamp_s,
                'timing_status':timing.timing_status.value,
                'width':original.width, 'height':original.height, 'dtype':'uint8',
                'role':role, 'review_target':role=='target', 'raw_png_relative_path':name, 'sha256':digest(data),
                'queue_item_ids':source.get('queue_item_ids', {}).get(index, [])})
    if not docs:
        raise ValueError('No review targets selected')
    package = ReviewPackage(manifest, scheme, docs, bases, images)
    ReviewPackage._from_files(package.files())
    return package


class ReviewFrameProvider:
    def __init__(self, package):
        self.package = package
        self.metadata = {(r['cine_id'],r['frame_index']):r for r in package.manifest['frames']}

    def available(self, cine_id, targets=False):
        return sorted(i for (cine,i),row in self.metadata.items() if cine == cine_id and (not targets or row['review_target']))

    def adjacent(self, cine_id, current, direction, targets=False):
        candidates = [i for i in self.available(cine_id, targets) if (i-current)*direction > 0]
        return (min(candidates) if direction > 0 else max(candidates)) if candidates else None

    def get_frame(self, cine_id, frame_index):
        row = self.metadata.get((cine_id,frame_index))
        if row is None:
            raise KeyError('This frame is not included in the review package')
        data = self.package.frames[row['raw_png_relative_path']]
        result = np.array(Image.open(BytesIO(data)), copy=True)
        result.setflags(write=False)
        return result
