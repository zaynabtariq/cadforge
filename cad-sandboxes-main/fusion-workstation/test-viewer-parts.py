"""Offline checks for body identity, instance placement and hidden geometry."""
import base64
import gzip
import importlib.util
from pathlib import Path
import struct
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
IDENTITY = [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]
FACET = struct.pack('<12fH', 0,0,1, 0,0,0, 10,0,0, 0,10,0, 0)
RAW = b'fixture'.ljust(80,b'\0') + struct.pack('<I',1) + FACET

class Exporter:
    def __init__(self): self.exported = []
    def createSTLExportOptions(self, body, path): return NS(body=body,path=path)
    def execute(self, options):
        self.exported.append(options.body)
        Path(options.path).write_bytes(RAW)
        return True

class PartsTests(unittest.TestCase):
    def setUp(self):
        fusion = NS(DistanceUnits=NS(MillimeterDistanceUnits=1),
                    MeshRefinementSettings=NS(MeshRefinementLow=1,MeshRefinementMedium=2,MeshRefinementHigh=3))
        self.body = NS(name='Bolt', entityToken='bolt', isVisible=True)
        hidden = NS(name='Hidden', entityToken='hidden', isVisible=False)
        # 90 degree rotation, translated by 2, 3, 4 cm in root coordinates.
        rotated = [0,-1,0,2, 1,0,0,3, 0,0,1,4, 0,0,0,1]
        def occurrence(path, matrix):
            return NS(fullPathName=path,isVisible=True,component=NS(bRepBodies=[self.body]),transform2=NS(asArray=lambda:matrix))
        self.exporter = Exporter()
        root = NS(bRepBodies=[self.body,hidden],allOccurrences=[occurrence('Assembly:1+Bolt:1',rotated),occurrence('Bolt:2',IDENTITY)])
        helpers = NS(get_design=lambda:NS(rootComponent=root,exportManager=self.exporter),app=NS(activeDocument=NS(name='Fixture')))
        spec=importlib.util.spec_from_file_location('viewer_parts_fixture', ROOT/'handlers_viewer.py')
        self.module=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'adsk':NS(fusion=fusion),'adsk.fusion':fusion,'bridge_helpers':helpers}):spec.loader.exec_module(self.module)

    def test_ranges_and_instances(self):
        result=self.module.snapshot({})
        self.assertEqual([(p['triangle_start'],p['triangle_count']) for p in result['parts']],[(0,1),(1,0),(1,1),(2,1)])
        self.assertEqual(len({p['id'] for p in result['parts']}),4)
        self.assertEqual(len(self.exporter.exported),3)
        raw=gzip.decompress(base64.b64decode(result['data_base64']))
        transformed=struct.unpack_from('<12fH',raw,134)
        self.assertEqual(transformed[:12],(0,0,1,20,30,40,20,40,40,10,30,40))
        self.assertEqual(len(raw),84+3*50)

    def test_conditional_capture_keeps_part_mapping(self):
        first=self.module.snapshot({})
        next_frame=self.module.snapshot({'if_none_match':first['sha256']})
        self.assertFalse(next_frame['changed'])
        self.assertNotIn('data_base64',next_frame)
        self.assertEqual(next_frame['parts'],first['parts'])

    def test_empty_workspace(self):
        self.module.bh.get_design().rootComponent.bRepBodies=[]
        self.module.bh.get_design().rootComponent.allOccurrences=[]
        result=self.module.snapshot({})
        self.assertEqual(result['parts'],[])
        self.assertEqual(result['triangles'],0)

if __name__=='__main__':unittest.main(verbosity=2)
