import sys
from pathlib import Path
import unittest
from dataclasses import replace
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from droplet_vision.annotations.magic_wand import (load_wand_config, grow_region, combine_selection,
                                                  mask_to_polygons, RegionTooLarge)
from droplet_vision.annotations.geometry import validate_geometry, nearest_polygon_segment


class WandTests(unittest.TestCase):
    def setUp(self):
        self.config = load_wand_config()
        y,x = np.ogrid[:256,:256]
        self.circle = (x-128)**2+(y-128)**2 <= 30**2
        self.image = np.where(self.circle,180,20).astype(np.uint8)

    def test_circle_raw_immutability_boundary_and_simplification(self):
        before=self.image.copy()
        mask,reference=grow_region(self.image,(128,128),10,8,self.config)
        np.testing.assert_array_equal(mask,self.circle)
        np.testing.assert_array_equal(self.image,before)
        self.assertEqual(reference,180)
        polygons=mask_to_polygons(mask,1.0)
        self.assertEqual(len(polygons),1)
        self.assertTrue(3<=len(polygons[0])<40)
        validate_geometry('polygon',{'points':polygons[0]},256,256)
        self.assertGreaterEqual(min(p[0] for p in polygons[0]),97.5)
        self.assertLessEqual(max(p[0] for p in polygons[0]),158.5)

    def test_tolerance_and_median_noise_seed(self):
        self.image[128,128]=0
        mask,reference=grow_region(self.image,(128,128),0,8,self.config)
        self.assertEqual(reference,180)
        self.assertFalse(mask[128,128])
        self.assertEqual(mask.sum(),self.circle.sum()-1)
        # No silent filling of the rejected noisy pixel/hole on conversion.
        with self.assertRaisesRegex(ValueError,'holes'): mask_to_polygons(mask)
        self.image[128,128]=170
        narrow,_=grow_region(self.image,(128,128),0,8,self.config)
        wide,_=grow_region(self.image,(128,128),10,8,self.config)
        self.assertEqual(wide.sum(),narrow.sum()+1)

    def test_four_eight_connectivity_and_corner_components(self):
        image=np.zeros((256,256),np.uint8)
        image[10:13,10:13]=200; image[13:16,13:16]=200
        four,_=grow_region(image,(11,11),0,4,self.config)
        eight,_=grow_region(image,(11,11),0,8,self.config)
        self.assertEqual(four.sum(),9); self.assertEqual(eight.sum(),18)
        self.assertEqual(len(mask_to_polygons(eight)),2)

    def test_replace_add_subtract_and_multiple_polygons(self):
        a=np.zeros((256,256),bool); a[20:50,20:50]=True
        b=np.zeros_like(a); b[80:100,80:100]=True
        combined=combine_selection(a,b,'add',.5)
        self.assertEqual(len(mask_to_polygons(combined)),2)
        np.testing.assert_array_equal(combine_selection(combined,b,'subtract',.5),a)
        np.testing.assert_array_equal(combine_selection(a,b,'replace',.5),b)
        self.assertFalse(np.shares_memory(combined,a))

    def test_region_limit_and_combined_limit(self):
        with self.assertRaises(RegionTooLarge): grow_region(np.zeros((256,256),np.uint8),(20,20),10,8,self.config)
        a=np.zeros((10,10),bool); a[:4]=True
        b=np.zeros_like(a); b[4:8]=True
        with self.assertRaises(RegionTooLarge): combine_selection(a,b,'add',.5)

    def test_edge_seed_and_invalid_input(self):
        image=np.zeros((256,256),np.uint8); image[:10,:10]=200
        mask,reference=grow_region(image,(0,0),10,8,self.config)
        self.assertEqual(reference,200); self.assertEqual(mask.sum(),100)
        for points in mask_to_polygons(mask): validate_geometry('polygon',{'points':points},256,256)
        for bad in (image.astype(np.uint16),np.zeros((10,10,3),np.uint8)):
            with self.assertRaises(ValueError): grow_region(bad,(0,0),10,8,self.config)
        with self.assertRaises(ValueError): grow_region(image,(-1,0),10,8,self.config)
        with self.assertRaises(ValueError): replace(self.config,max_region_fraction=0)

    def test_nearest_segment_projection_and_closing_edge(self):
        points=[[20,20],[100,20],[100,100],[20,100]]
        self.assertEqual(nearest_polygon_segment(points,[70,22])[:2],(0,[70,20]))
        self.assertEqual(nearest_polygon_segment(points,[18,60])[:2],(3,[20,60]))

    def test_backend_has_no_qt_dependency(self):
        import subprocess
        code="import sys; from droplet_vision.annotations.magic_wand import load_wand_config; load_wand_config(); assert not any(x.startswith('PySide6') for x in sys.modules)"
        import os
        env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1]/'src'))
        subprocess.run([sys.executable,'-B','-c',code],env=env,check=True)
