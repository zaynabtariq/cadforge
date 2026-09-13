import numpy as np
import pytest
import trimesh
import cadquery as cq
from cadforge.protected_edit import resize_preserving_holes
from cadforge.robotics import RobotLinkSpec,build_link


def stl(shape,path):
    cq.exporters.export(shape,str(path));return trimesh.load(path,force='mesh')


def test_actual_robot_link_stl_width_change_preserves_pivots(tmp_path):
    mesh=stl(build_link(RobotLinkSpec()).shape,tmp_path/'link.stl')
    result,checks,features=resize_preserving_holes(mesh,'y',28)
    assert len(features)==2
    assert result.extents[1]==pytest.approx(28)
    assert all(c['passed'] for c in checks)
    assert sorted(round(f['center'][0],5) for f in features)==[-40,40]
    assert np.array_equal(mesh.vertices[:,2],result.vertices[:len(mesh.vertices),2])


def test_independent_two_hole_plate(tmp_path):
    plate=cq.Workplane('XY').box(60,30,4)
    plate=plate.faces('>Z').workplane().pushPoints([(-12,0),(12,0)]).hole(6)
    mesh=stl(plate.val(),tmp_path/'plate.stl');original=mesh.vertices.copy()
    result,checks,features=resize_preserving_holes(mesh,'x',80)
    assert len(features)==2 and all(abs(f['radius_mm']-3)<1e-4 for f in features)
    assert result.extents[0]==pytest.approx(80)
    assert np.array_equal(mesh.vertices,original)


def test_non_z_holes_and_shrink_and_aggressive_edit_rejected(tmp_path):
    mesh=stl(build_link(RobotLinkSpec()).shape,tmp_path/'link.stl')
    original=mesh.vertices.copy()
    for target in [10,1000]:
        with pytest.raises(ValueError):resize_preserving_holes(mesh,'y',target)
    rotated=mesh.copy();rotated.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2,[0,1,0]))
    with pytest.raises(ValueError):resize_preserving_holes(rotated,'y',28)
    assert np.array_equal(mesh.vertices,original)


def test_solid_outer_cylinder_not_misrecognized():
    with pytest.raises(ValueError,match='No complete'):
        resize_preserving_holes(trimesh.creation.cylinder(radius=5,height=10),'x',15)


def test_normalized_intersection_policy_still_rejects_true_crossing():
    from cadforge.protected_edit import _numerical_check_mesh
    from cadforge.region_edit import _intersecting_pairs
    a=trimesh.creation.box(extents=[10,10,10]);b=a.copy();b.apply_translation([3,3,3])
    crossing=trimesh.util.concatenate([a,b])
    assert _intersecting_pairs(_numerical_check_mesh(crossing),np.arange(len(crossing.faces))) is not None


def test_physical_face_area_floor_remains_unscaled():
    from cadforge.region_edit import _validate
    # This isolated guard test verifies no normalization is used for physical area.
    tiny=trimesh.creation.box(extents=[1e-6,1e-6,1e-6])
    checks=_validate(tiny,tiny.copy(),np.ones(len(tiny.vertices),dtype=bool))
    assert any(c['name']=='no_collapsed_faces' and not c['passed'] for c in checks)


def test_public_coaxial_profile_protection_when_fixture_available():
    from pathlib import Path
    from cadforge.profile_recognition import recognize_coaxial_holes
    path=Path(__file__).resolve().parents[1]/'artifacts/region-public/plate_holes.STL'
    if not path.exists():pytest.skip('Downloaded public development fixture not available')
    mesh=trimesh.load(path,force='mesh')
    recognized,indices=recognize_coaxial_holes(mesh)
    result,checks,features=resize_preserving_holes(mesh,'x',float(mesh.extents[0]+20))
    assert len(features)==5
    assert np.array_equal(mesh.vertices[indices],result.vertices[indices])
    assert all(c['passed'] for c in checks)
    assert result.extents[0]==pytest.approx(mesh.extents[0]+20)
    assert any(f['profile']['annular_shoulder_triangle_count']>0 for f in features)
