import json
import subprocess
import sys
import cadquery as cq
from cadforge.schema import DesignSpec
from cadforge.enhanced_geometry import build_design, export_design, validate_enhanced_design

def test_generated_python_regenerates_real_editable_model(tmp_path):
    base=build_design(DesignSpec(family='glasses',parameters={'board_width':30}))
    files=export_design(base,tmp_path)
    subprocess.run([sys.executable,files['python']],check=True,capture_output=True,timeout=30)
    fresh=cq.importers.importStep(str(tmp_path/'regenerated'/'design.step')).val()
    original=cq.importers.importStep(files['step']).val()
    assert abs(fresh.Volume()-original.Volume())<1e-5
    edited=build_design(DesignSpec(family='glasses',parameters={'board_width':35}))
    assert validate_enhanced_design(edited).passed
    assert abs(edited.parts['housing'].BoundingBox().ylen-base.parts['housing'].BoundingBox().ylen-5)<1e-5
