"""Independent public development counterexamples for cable contract gates.

Synthetic bend requirements below test logic, not a real cable specification.
The material box is far from every route so clearance cannot mask bend errors.
"""
import cadquery as cq
import pytest
from cadforge.engineering import Cable,EngineeringContract,assess_geometry


@pytest.fixture(scope='module')
def material():
    return {'remote_box':cq.Workplane('XY').box(1,1,1).translate((100,100,100)).val()}


def report(material,points,minimum=2,radius=.001):
    cable=Cable('probe',tuple(points),radius,minimum,'Synthetic test bend requirement')
    return {gate.name:gate.status for gate in assess_geometry(material,EngineeringContract(cables=(cable,))).gates}


@pytest.mark.parametrize('scale',[.0001,.01,1.,10.])
@pytest.mark.parametrize('corner',[45,90])
def test_polyline_corner_fails_independently_of_segment_scale(material,scale,corner):
    points=((0,0,0),(scale,0,0),(2*scale if corner==45 else scale,scale,0))
    gates=report(material,points)
    assert gates['cable.probe.clearance']=='pass'
    assert gates['cable.probe.bend']=='fail'


@pytest.mark.parametrize('points',[
    ((0,0,0),(1,0,0)),
    ((0,0,0),(.0001,0,0),(.0002,0,0)),
    ((0,0,0),(1,2,3),(2,4,6)),
])
def test_valid_straight_route_positive_control(material,points):
    gates=report(material,points)
    assert gates['cable.probe.clearance']=='pass'
    assert gates['cable.probe.bend']=='pass'


@pytest.mark.parametrize('points',[
    ((0,0,0),(0,0,0)),
    ((0,0,0),(1,0,0),(1,0,0)),
])
def test_zero_length_segment_is_invalid_contract(material,points):
    with pytest.raises(ValueError):report(material,points)


@pytest.mark.parametrize('minimum',[0,-2,float('nan'),float('inf')])
def test_nonpositive_or_nonfinite_bend_requirement_rejected(material,minimum):
    with pytest.raises(ValueError):report(material,((0,0,0),(1,0,0)),minimum=minimum)


def test_unspecified_bend_requirement_stays_blocked(material):
    gates=report(material,((0,0,0),(1,0,0)),minimum=None)
    assert gates['cable.probe.bend']=='blocked'


def test_reversal_is_not_straight_continuation(material):
    gates=report(material,((0,0,0),(.0001,0,0),(0,0,0)))
    assert gates['cable.probe.bend']=='fail'


@pytest.mark.parametrize('points',[
    ((0,0),(1,0)),
    ((0,0,0),(True,0,0)),
    ((0,0,0),('1',0,0)),
])
def test_bad_point_shape_rejected_before_geometry(points):
    # An opaque object makes accidental CAD access fail rather than hide the
    # contract error behind kernel behavior.
    with pytest.raises(ValueError):report({'sentinel':object()},points)


@pytest.mark.parametrize('radius',[0,-1,True])
def test_bad_radius_rejected_before_geometry(radius):
    with pytest.raises(ValueError):report({'sentinel':object()},((0,0,0),(1,0,0)),radius=radius)
