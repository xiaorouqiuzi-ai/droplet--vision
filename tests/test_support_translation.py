"""Sparse, raw-coordinate translation without mutating immutable source records."""
import unittest
import tempfile
from copy import deepcopy
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from droplet_vision.annotations import AnnotationDocument
from droplet_vision.annotations.support_translation import translated
from test_support_templates import rod


class SupportTranslationTests(unittest.TestCase):
    def setUp(self):
        self.doc=AnnotationDocument('test','test.cine',100,500,32,32)
        self.rods=[rod(self.doc,499),rod(self.doc,499,8)]
        value=self.doc.support_template_from([r.annotation_id for r in self.rods])
        value['support_structure']['apply_entire_cine']=True
        self.doc.replace_cine_templates(value)

    def offset(self,frame,dx,dy):
        self.doc.replace_cine_templates(self.doc.with_support_translation(frame,{'dx':dx,'dy':dy}))

    def test_sparse_group_geometry_zero_reset_and_source_frame(self):
        original=[r.to_dict() for r in self.rods]
        self.assertEqual(self.doc.support_translation(100),{'dx':0,'dy':0})
        self.offset(200,2,-1)
        self.offset(100,3,4)
        for frame,offset in ((200,{'dx':2,'dy':-1}),(100,{'dx':3,'dy':4})):
            projections=self.doc.support_projections(frame)
            self.assertEqual([r.geometry for r in projections],[translated(r.geometry,offset) for r in self.rods])
        self.assertEqual(len(self.doc.records.records()),2)
        self.assertEqual(len(self.doc.cine_templates['support_structure']['frame_overrides']),2)
        self.offset(499,1,1)
        self.assertEqual(len(self.doc.support_projections(499)),2)
        self.assertEqual(self.doc.support_suppressed_ids(499),{r.annotation_id for r in self.rods})
        self.assertEqual([self.doc.records.get(r.annotation_id).to_dict() for r in self.rods],original)
        self.offset(100,0,0)
        self.assertNotIn('100',self.doc.cine_templates['support_structure']['frame_overrides'])
        self.assertEqual([r.geometry for r in self.doc.support_projections(100)],[r.geometry for r in self.rods])
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'annotations.json';self.doc.save(path)
            loaded=AnnotationDocument.load(path)
            self.assertEqual(loaded.to_dict(),self.doc.to_dict())
            self.assertEqual(loaded.support_projections(200)[0].geometry,self.doc.support_projections(200)[0].geometry)

    def test_validation_old_document_and_bounds(self):
        self.assertNotIn('frame_overrides',self.doc.cine_templates['support_structure'])
        old=AnnotationDocument.from_dict(self.doc.to_dict())
        self.assertEqual(old.support_translation(200),{'dx':0,'dy':0})
        for offset in ({'dx':True,'dy':0},{'dx':float('nan'),'dy':0},{'dx':0},{'dx':100,'dy':0}):
            with self.assertRaises(ValueError): self.doc.with_support_translation(200,offset)
        for frame in (-1,500,True,1.5):
            with self.assertRaises(ValueError): self.doc.with_support_translation(frame,{'dx':1,'dy':0})
        for key in ('001','-1','500','x'):
            value=self.doc.to_dict()
            value['cine_templates']['support_structure']['frame_overrides']={key:{'translation':{'dx':1,'dy':0}}}
            with self.assertRaises(ValueError): AnnotationDocument.from_dict(value)

    def test_package_translated_snapshot_review_and_concurrent_offset_conflict(self):
        import numpy as np
        from droplet_vision.annotations.scheme import load_scheme
        from droplet_vision.review_package import export_package, ReviewPackage, merge_review
        from droplet_vision.schema import FrameResult
        self.doc.scheme=load_scheme();self.offset(200,2,-1)
        canonical=self.doc.to_dict()
        source={'document':self.doc,'targets':[200],
                'get_frame':lambda i:np.full((32,32),40,np.uint8),
                'get_metadata':lambda i:FrameResult(self.doc.cine_id,i)}
        package=export_package([source],self.doc.scheme,context=0)
        remote=package.documents[self.doc.cine_id]
        self.assertEqual(remote.cine_templates,{})
        original=remote.active_records()[0]
        self.assertEqual(original.geometry,translated(self.rods[0].geometry,{'dx':2,'dy':-1}))
        self.assertEqual(original.attributes['frame_translation'],{'dx':2,'dy':-1})
        derived=remote.derive(original.annotation_id,translated(original.geometry,{'dx':1,'dy':0}))
        remote.add_record(derived,'reviewed');remote.transition(deactivate=[original.annotation_id])
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'translation.dvrpkg';package.save(path);package=ReviewPackage.open(path)
        result,conflicts=merge_review(self.doc,package)
        self.assertEqual(conflicts,[])
        self.assertEqual(self.doc.to_dict(),canonical)
        self.assertEqual(result.cine_templates,self.doc.cine_templates)
        self.assertIn(derived.annotation_id,result.active_annotation_ids)
        self.assertEqual(result.record_layers[derived.annotation_id],'reviewed')
        self.assertEqual(len(result.support_projections(200)),1)
        self.offset(200,3,-1)
        _,conflicts=merge_review(self.doc,package)
        self.assertEqual(len(conflicts),1)
        self.offset(499,1,0)
        from droplet_vision.review_package.bundle import snapshot
        snap=snapshot(self.doc,{499})
        self.assertEqual(len(snap.active_records()),2)
        self.assertTrue(all(r.attributes.get('frame_translation')=={'dx':1,'dy':0} for r in snap.active_records()))
        self.assertEqual(snap.cine_templates,{})


if __name__=='__main__': unittest.main()
