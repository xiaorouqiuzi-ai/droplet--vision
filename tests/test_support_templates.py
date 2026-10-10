"""Cine-local confirmed templates and portable, independent current-frame copies."""
import sys
from pathlib import Path
import tempfile
import unittest
from copy import deepcopy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from droplet_vision.annotations import AnnotationDocument, AnnotationRecord


def rod(doc, frame=0, offset=0):
    record = AnnotationRecord(doc.cine_id, frame, 'support_structure', 'polygon',
                              {'points':[[2+offset,2],[4+offset,2],[4+offset,20],[2+offset,20]]})
    doc.add_record(record)
    return record


class SupportTemplateTests(unittest.TestCase):
    def test_display_metadata_validation_and_safe_fallback(self):
        from droplet_vision.annotations.scheme import load_scheme
        from droplet_vision.annotations.display_style import resolve_display
        scheme = load_scheme()
        display, warning = resolve_display(scheme)
        self.assertIsNone(warning)
        self.assertEqual(display['instance_prefixes']['support_structure'], 'SupportRod')
        self.assertEqual(display['object_display_names']['support_structure']['zh_CN'], '载滴杆')
        for invalid in ([], {'unknown': 'Rod'}, {'support_structure': ''}):
            scheme['display']['instance_prefixes'] = invalid
            with self.assertLogs('droplet_vision.annotations.display_style', level='WARNING'):
                safe, warning = resolve_display(scheme)
            self.assertTrue(warning)
            self.assertNotIn('instance_prefixes', safe)

    def setUp(self):
        self.doc = AnnotationDocument('sample', 'sample.cine', 100, 100, 32, 32)
        self.sources = [rod(self.doc), rod(self.doc, offset=8)]
        self.doc.replace_cine_templates(self.doc.support_template_from([r.annotation_id for r in self.sources]))

    def test_copy_set_provenance_isolation_and_dedup_after_edit(self):
        original = [r.to_dict() for r in self.sources]
        copies = self.doc.make_support_copies(50, {'raw_time64':123456789, 'relative_timestamp_s':.25})
        self.assertEqual(len(copies),2)
        for index, (source, copy) in enumerate(zip(self.sources, copies),1):
            self.assertEqual(copy.geometry,source.geometry)
            self.assertEqual(copy.frame_index,50)
            self.assertEqual(copy.source,'manual')
            self.assertEqual(copy.review_status,'unreviewed')
            self.assertIsNone(copy.derived_from)
            self.assertEqual(copy.attributes['instance_name'],f'SupportRod_{index:02d}')
            self.assertEqual(copy.attributes['template_source_annotation_id'],source.annotation_id)
            self.assertEqual(copy.attributes['template_source_frame_index'],0)
            self.assertEqual(copy.attributes['raw_time64'],123456789)
            self.doc.add_record(copy)
        self.assertEqual(self.doc.make_support_copies(50),[])
        geometry = deepcopy(copies[0].geometry);geometry['points'][0][0] += 1
        derived = self.doc.derive(copies[0].annotation_id,geometry)
        self.doc.add_record(derived)
        self.doc.transition(deactivate=[copies[0].annotation_id])
        self.assertEqual(self.doc.make_support_copies(50),[])
        self.assertEqual([self.doc.records.get(r.annotation_id).to_dict() for r in self.sources],original)
        self.assertEqual(self.doc.make_support_copies(60)[0].geometry,self.sources[0].geometry)

    def test_old_document_and_save_reload_keep_pointers_and_dirty(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'annotations.json';self.doc.save(path)
            loaded=AnnotationDocument.load(path)
            self.assertEqual(loaded.cine_templates,self.doc.cine_templates)
            self.assertFalse(loaded.dirty)
            self.assertEqual(len(loaded.make_support_copies(20)),2)
        legacy=self.doc.to_dict();legacy.pop('cine_templates')
        loaded=AnnotationDocument.from_dict(legacy)
        self.assertEqual(loaded.cine_templates,{})
        self.assertNotIn('cine_templates',loaded.to_dict())
        detached=self.doc.cine_templates
        detached['support_structure']['annotation_ids'].clear()
        self.assertEqual(len(self.doc.cine_templates['support_structure']['annotation_ids']),2)

    def test_explicit_update_and_invalid_templates(self):
        new=rod(self.doc,10,offset=3)
        before=self.doc.cine_templates
        self.doc.replace_cine_templates(self.doc.support_template_from([new.annotation_id]))
        self.assertEqual(self.doc.make_support_copies(20)[0].geometry,new.geometry)
        self.doc.replace_cine_templates(before)
        for value in ({'support_structure':{'source_frame_index':0,'annotation_ids':['missing']}},
                      {'support_structure':{'source_frame_index':10,'annotation_ids':[self.sources[0].annotation_id]}},
                      {'support_structure':{'source_frame_index':0,'annotation_ids':[]}}):
            with self.assertRaises(ValueError): self.doc.replace_cine_templates(value)
        with self.assertRaises(ValueError):
            self.doc.support_template_from([new.annotation_id,self.sources[0].annotation_id])
        self.assertEqual(self.doc.cine_templates,before)

    def test_package_without_source_frame_preserves_copies_and_local_template(self):
        import numpy as np
        from droplet_vision.annotations.scheme import load_scheme
        from droplet_vision.review_package import export_package, ReviewPackage, merge_review
        from droplet_vision.schema import FrameResult
        self.doc.scheme=load_scheme()
        for copy in self.doc.make_support_copies(50): self.doc.add_record(copy)
        source={'document':self.doc,'targets':[50],
                'get_frame':lambda i:np.full((32,32),40,np.uint8),
                'get_metadata':lambda i:FrameResult(self.doc.cine_id,i)}
        package=export_package([source],self.doc.scheme,context=0)
        remote=package.documents[self.doc.cine_id]
        self.assertEqual(remote.cine_templates,{})
        self.assertEqual({r.frame_index for r in remote.records.records()},{50})
        original=remote.active_records()[0]
        changed=remote.derive(original.annotation_id,{'points':[[5,2],[7,2],[7,20]]})
        remote.add_record(changed,'reviewed')
        remote.transition(deactivate=[original.annotation_id])
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'review.dvrpkg';package.save(path)
            package=ReviewPackage.open(path)
        candidate=package.documents[self.doc.cine_id].records.get(changed.annotation_id)
        self.assertEqual(candidate.attributes['template_source_annotation_id'],self.sources[0].annotation_id)
        result, conflicts = merge_review(self.doc, package)
        self.assertFalse(conflicts)
        self.assertEqual(result.cine_templates,self.doc.cine_templates)
        self.assertEqual(self.doc.make_support_copies(60)[0].geometry,self.sources[0].geometry)

    def test_package_can_keep_source_metadata_without_changing_template(self):
        from droplet_vision.review_package.bundle import snapshot
        exported=snapshot(self.doc,{0})
        self.assertEqual(exported.cine_templates,self.doc.cine_templates)

    def test_global_projection_and_legacy_default_off(self):
        self.assertEqual(self.doc.support_projections(50), [])
        value=self.doc.cine_templates
        value['support_structure']['apply_entire_cine']=True
        self.doc.replace_cine_templates(value)
        before=self.doc.to_dict()
        for frame in (0,50,99):
            projections=self.doc.support_projections(frame)
            self.assertEqual(len(projections),0 if frame==0 else 2)
        self.assertEqual(self.doc.to_dict(),before)
        loaded=AnnotationDocument.from_dict(before)
        self.assertEqual(len(loaded.support_projections(99)),2)
        value['support_structure']['apply_entire_cine']='yes'
        with self.assertRaises(ValueError): loaded.replace_cine_templates(value)
        self.assertEqual(loaded.to_dict(),before)

    def test_global_projection_package_materialization_and_review_import(self):
        import numpy as np
        from droplet_vision.annotations.scheme import load_scheme
        from droplet_vision.review_package import export_package, ReviewPackage, merge_review
        from droplet_vision.schema import FrameResult
        self.doc.scheme=load_scheme()
        value=self.doc.cine_templates;value['support_structure']['apply_entire_cine']=True
        self.doc.replace_cine_templates(value)
        canonical=self.doc.to_dict()
        source={'document':self.doc,'targets':[50],
                'get_frame':lambda i:np.full((32,32),40,np.uint8),
                'get_metadata':lambda i:FrameResult(self.doc.cine_id,i)}
        package=export_package([source],self.doc.scheme,context=1)
        self.assertEqual(self.doc.to_dict(),canonical)
        remote=package.documents[self.doc.cine_id]
        self.assertEqual(remote.cine_templates,{})
        self.assertEqual({r.frame_index for r in remote.records.records()},{49,50,51})
        self.assertEqual(len(remote.active_records()),6)
        original=remote.active_records(50)[0]
        self.assertEqual(original.source,'imported')
        self.assertEqual(original.attributes['creation_tool'],'cine_template_projection')
        changed=remote.derive(original.annotation_id,{'points':[[6,2],[9,2],[9,20]]})
        remote.add_record(changed,'reviewed');remote.transition(deactivate=[original.annotation_id])
        self.assertEqual(changed.attributes['creation_tool'],'cine_support_template_override')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'projection.dvrpkg';package.save(path);package=ReviewPackage.open(path)
        result, conflicts=merge_review(self.doc,package)
        self.assertEqual(conflicts,[])
        self.assertEqual(self.doc.to_dict(),canonical)
        self.assertEqual(result.cine_templates,self.doc.cine_templates)
        self.assertEqual(result.record_layers[changed.annotation_id],'reviewed')
        self.assertIn(changed.annotation_id,result.active_annotation_ids)
        self.assertEqual(len(result.support_projections(50)),1)
        self.assertEqual(len(result.support_projections(60)),2)
        result.transition(deactivate=[changed.annotation_id])
        self.assertEqual(len(result.support_projections(50)),2)
        # A concurrent local override must require an explicit import decision.
        local=self.doc.make_support_copies(50)[0]
        local.attributes['creation_tool']='cine_support_template_override'
        self.doc.add_record(local)
        blocked, conflicts=merge_review(self.doc,package)
        self.assertEqual(len(conflicts),1)
        self.assertNotIn(changed.annotation_id,blocked.active_annotation_ids)
        self.assertEqual(blocked.cine_templates,self.doc.cine_templates)


if __name__ == '__main__':
    unittest.main()
