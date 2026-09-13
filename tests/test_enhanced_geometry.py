import pytest
from cadforge.schema import DesignSpec
from cadforge.enhanced_geometry import build_design, validate_enhanced_design
from cadforge.enhanced_geometry import export_design

@pytest.mark.parametrize('family',['glasses','enclosure'])
def test_enhanced_camera_and_fasteners(family,tmp_path):
    design=build_design(DesignSpec(family=family))
    report=validate_enhanced_design(design)
    assert report.passed,[c for c in report.checks if not c.passed]
    assert len([n for n in design.parts if 'screw' in n])>=6
    assert report.measurements['camera_component_clearance_mm']>=.2-1e-6
    paths=export_design(design,tmp_path)
    assert (tmp_path/'design.step').exists()
    assert 'from cadforge.enhanced_geometry import' in (tmp_path/'design.py').read_text()

def test_camera_hole_block_detected():
    design=build_design(DesignSpec(family='enclosure'))
    design.parts['housing']=design.parts['housing'].fuse(design.probes['camera_lens_opening'])
    report=validate_enhanced_design(design)
    assert not report.passed
    assert any(c.name=='camera_lens_opening' and not c.passed for c in report.checks)


def test_floating_lid_and_blocked_screw_are_detected():
    design=build_design(DesignSpec(family='enclosure'))
    design.parts['lid']=design.parts['lid'].translate((0,0,3))
    design.parts['housing']=design.parts['housing'].fuse(design.probes['pi_screw_hole_0'])
    report=validate_enhanced_design(design)
    failed={c.name for c in report.checks if not c.passed}
    assert 'lid_seated' in failed
    assert 'pi_screw_hole_0' in failed
