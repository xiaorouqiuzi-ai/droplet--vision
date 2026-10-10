import tempfile
from copy import deepcopy
from pathlib import Path
import unittest

from test_uniform_annotation_package import empty_package
from droplet_vision.annotations import AnnotationDocument, AnnotationRecord
from droplet_vision.annotations.support_translation import translated
from droplet_vision.review_package import AnnotationPackage, merge_review


def setup_rods(package):
    doc = next(iter(package.documents.values()))
    last = max(row['frame_index'] for row in package.manifest['frames'])
    records = []
    for x in (5, 10):
        record = AnnotationRecord(doc.cine_id, last, 'support_structure', 'polygon',
                                  {'points': [[x,5],[x+1,5],[x+1,12],[x,12]]})
        doc.add_record(record)
        records.append(record)
    value = doc.support_template_from([r.annotation_id for r in records])
    value['support_structure']['enabled'] = True
    doc.replace_support_templates(value)
    return doc, records


class PackageSupportScopeTests(unittest.TestCase):
    def test_twenty_frames_no_copies_domain_and_old_package(self):
        _, _, package = empty_package(samples=20)
        doc, rods = setup_rods(package)
        available = {r['frame_index'] for r in package.manifest['frames']}
        self.assertEqual(len(available), 20)
        for frame in available:
            self.assertEqual([r.geometry for r in doc.support_group(frame)], [r.geometry for r in rods])
        missing = next(i for i in range(doc.frame_count) if i not in available)
        self.assertEqual(doc.support_group(missing), [])
        self.assertEqual(doc.support_projections(missing), [])
        with self.assertRaises(ValueError):
            doc.with_support_translation(missing, {'dx':1,'dy':0})
        self.assertEqual(len(doc.records.records()), 2)
        self.assertEqual(doc.cine_templates, {})
        self.assertEqual(package.progress(doc.cine_id), (20,1,19))
        _, _, legacy = empty_package(samples=20)
        self.assertNotIn('package_templates', next(iter(legacy.documents.values())).to_dict())
        legacy.manifest['package_format_version'] = 1
        legacy.manifest.pop('package_kind'); legacy.manifest.pop('package_purpose')
        for meta in legacy.manifest['base_annotation_documents'].values():
            meta.pop('standalone_empty_base', None)
        # Legacy format may retain its existing uniform metadata; no new templates inferred.
        opened = AnnotationPackage._from_files(legacy.files())
        self.assertEqual(next(iter(opened.documents.values())).package_templates, {})

    def test_offsets_independent_roundtrip_and_invalid_domain(self):
        _, _, package = empty_package(samples=20)
        doc, rods = setup_rods(package)
        indices = package.manifest['sampling']['frame_indices'] if 'sampling' in package.manifest else sorted({r['frame_index'] for r in package.manifest['frames']})
        a,b,c = indices[:3]
        for frame, offset in [(b, {'dx':2,'dy':-1}), (c, {'dx':-4,'dy':3})]:
            doc.replace_support_templates(doc.with_support_translation(frame,offset))
            self.assertEqual([r.geometry for r in doc.support_group(frame)], [translated(r.geometry,offset) for r in rods])
        self.assertEqual(doc.support_group(a)[0].geometry, rods[0].geometry)
        self.assertEqual(len(doc.records.records()), 2)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'scope.dvapkg'; package.save(path)
            reloaded = AnnotationPackage.open(path).documents[doc.cine_id]
            self.assertEqual(reloaded.package_templates, doc.package_templates)
            self.assertEqual(reloaded.support_group(c)[0].geometry, doc.support_group(c)[0].geometry)
        invalid = deepcopy(doc.to_dict())
        invalid['package_templates']['support_structure']['apply_entire_cine'] = True
        with self.assertRaises(ValueError): AnnotationDocument.from_dict(invalid)
        doc._package_templates['support_structure']['frame_overrides']['1'] = {'translation': {'dx':1,'dy':0}}
        with self.assertRaises(ValueError): AnnotationPackage._from_files(package.files())

    def test_returned_candidate_preserves_canonical_and_is_idempotent(self):
        local, _, package = empty_package(samples=20)
        remote, rods = setup_rods(package)
        frame = package.manifest['frames'][1]['frame_index']
        remote.replace_support_templates(remote.with_support_translation(frame, {'dx':2,'dy':-1}))
        own = AnnotationRecord(local.cine_id, 0, 'support_structure','polygon',{'points':[[1,1],[2,1],[2,8]]})
        local.add_record(own)
        value = local.support_template_from([own.annotation_id]);value['support_structure']['apply_entire_cine']=True
        local.replace_cine_templates(value)
        before = local.to_dict()
        merged, conflicts = merge_review(local, package)
        self.assertFalse(conflicts)
        self.assertEqual(local.to_dict(), before)
        self.assertEqual(merged.cine_templates, local.cine_templates)
        self.assertEqual(merged.package_templates, {})
        candidates = [h['candidate'] for h in merged.history if h['action']=='import_package_support_template_candidate']
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate['status'], 'reviewed_candidate')
        self.assertEqual(candidate['package_templates'], remote.package_templates)
        self.assertEqual(candidate['provenance']['package_id'], package.manifest['package_id'])
        self.assertEqual(candidate['source_records'][0]['geometry'], rods[0].geometry)
        again, _ = merge_review(merged, package)
        self.assertEqual(sum(h['action']=='import_package_support_template_candidate' for h in again.history), 1)

    def test_cine_state_retained_but_never_used_as_package_scope(self):
        original, _, package = empty_package(samples=20)
        doc, rods = setup_rods(package)
        # Independent snapshots can coexist without sharing enabled/offset state.
        cine = {'support_structure': {'source_frame_index':99, 'annotation_ids':[rods[0].annotation_id], 'apply_entire_cine':True}}
        doc.replace_cine_templates(cine)
        value = doc.package_templates;value['support_structure']['enabled']=False
        doc.replace_support_templates(value)
        self.assertEqual(doc.support_projections(0), [])
        self.assertEqual(doc.cine_templates, cine)
        self.assertTrue(original.support_scope.kind == 'cine')
