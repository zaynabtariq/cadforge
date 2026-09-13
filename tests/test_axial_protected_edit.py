import numpy as np
import cadquery as cq
import trimesh
import pytest
from cadforge.robotics import RobotLinkSpec,build_link
from cadforge.axial_protected_edit import resize_preserving_axial_holes
from cadforge.protected_edit import _recognized


def test_rotated_robot_width_preserves_world_pivots(tmp_path):
    path=tmp_path/'link.stl';cq.exporters.export(build_link(RobotLinkSpec()).shape,str(path))
    source=trimesh.load(path,force='mesh');_,protected=_recognized(source)
    mesh=source.copy();mesh.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2,[0,1,0]))
    before=mesh.vertices.copy()
    changed,checks,features=resize_preserving_axial_holes(mesh,'y',28)
    assert changed.extents[1]==pytest.approx(28)
    assert np.array_equal(changed.vertices[protected],before[protected])
    assert np.array_equal(mesh.vertices,before)
    assert all(c['passed'] for c in checks)
    assert all(f['local_to_world_axes']==[1,2,0] for f in features)


def test_oblique_bores_remain_unsupported(tmp_path):
    path=tmp_path/'link.stl';cq.exporters.export(build_link(RobotLinkSpec()).shape,str(path))
    mesh=trimesh.load(path,force='mesh');mesh.apply_transform(trimesh.transformations.rotation_matrix(.3,[0,1,0]))
    with pytest.raises(ValueError,match='unambiguous'):resize_preserving_axial_holes(mesh,'y',28)


def test_height_expansion_requires_perpendicular_bore(tmp_path):
    path=tmp_path/'link.stl';cq.exporters.export(build_link(RobotLinkSpec()).shape,str(path))
    original=trimesh.load(path,force='mesh')
    with pytest.raises(ValueError,match='bore direction'):
        resize_preserving_axial_holes(original,'z',original.extents[2]+10)
    _,protected=_recognized(original)
    mesh=original.copy()
    mesh.vertices=np.asarray(mesh.vertices)[:,[2,0,1]]
    before=mesh.vertices.copy()
    changed,checks,_=resize_preserving_axial_holes(mesh,'z',mesh.extents[2]+10)
    assert changed.extents[2]==pytest.approx(mesh.extents[2]+10)
    assert np.array_equal(changed.vertices[protected],before[protected])
    assert np.array_equal(mesh.vertices,before)
    assert all(c['passed'] for c in checks)
