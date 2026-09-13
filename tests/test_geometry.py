import json
import pytest
import cadquery as cq
from cadforge.schema import DesignSpec
from cadforge.geometry import build_design, export_design, box
from cadforge.validation import validate_design

@pytest.mark.parametrize('family', ['glasses','enclosure','bracket','clip'])
def test_real_geometry_and_editable_exports(family,tmp_path):
    built=build_design(DesignSpec(family=family))
    report=validate_design(built)
    assert report.passed, [c for c in report.checks if not c.passed]
    paths=export_design(built,tmp_path)
    imported=cq.importers.importStep(paths['step']).val()
    assert imported.isValid() and imported.Volume()>0
    assert json.loads(open(paths['json']).read())['family']==family
    assert 'SPEC =' in open(paths['python']).read()
    assert (tmp_path/'design.stl').stat().st_size>100

def test_failure_feedback_thin_wall_then_repair():
    initial=validate_design(build_design(DesignSpec(family='enclosure',parameters={'wall':.7})))
    assert not initial.passed
    assert any(c.name=='minimum_wall' and not c.passed for c in initial.checks)
    assert validate_design(build_design(DesignSpec(family='enclosure',parameters={'wall':1.6}))).passed

def test_collision_is_measured():
    built=build_design(DesignSpec(family='enclosure'))
    built.parts['lid']=built.parts['housing']
    assert not validate_design(built).passed

def test_filled_camera_hole_fails():
    built=build_design(DesignSpec(family='enclosure'))
    built.parts['housing']=built.parts['housing'].fuse(built.probes['camera_aperture'])
    report=validate_design(built)
    assert any(c.name=='camera_aperture' and not c.passed for c in report.checks)

def test_ir_dimension_tampering_fails():
    built=build_design(DesignSpec(family='enclosure'))
    built.spec.parameters['board_length']=80
    assert not validate_design(built).passed

@pytest.mark.parametrize('value',[0,-1,float('nan'),float('inf')])
def test_degenerate_parameters_rejected(value):
    with pytest.raises(ValueError):
        build_design(DesignSpec(family='clip',parameters={'wall':value}))


@pytest.mark.parametrize('diameter',[2.0,2.5,3.0])
def test_enclosure_external_lugs_have_real_through_holes(diameter):
    design=build_design(DesignSpec(family='enclosure',parameters={'screw_diameter':diameter}))
    p=design.spec.resolved()
    original_x=p['board_length']+2*p['clearance']+2*p['wall']
    assert design.parts['housing'].BoundingBox().xlen==pytest.approx(original_x+diameter+2*p['wall'])
    for name in ('housing','lid'):
        radii=[face._geomAdaptor().Cylinder().Radius() for face in design.parts[name].Faces() if face.geomType()=='CYLINDER']
        assert sum(abs(radius-diameter/2)<1e-6 for radius in radii)>=2
        for index in (0,1):
            assert design.parts[name].intersect(design.probes[f'screw_aperture_{index}']).Volume()<1e-6
    # Preserved cavity still fits the same board at the same world position.
    assert design.parts['housing'].intersect(design.probes['component_clearance']).Volume()<1e-6


def test_enclosure_filled_mounting_hole_fails():
    design=build_design(DesignSpec(family='enclosure'))
    design.parts['housing']=design.parts['housing'].fuse(design.probes['screw_aperture_0'])
    assert any(c.name=='screw_aperture_0' and not c.passed for c in validate_design(design).checks)
