from pathlib import Path
import numpy as np
import pytest
import trimesh
import cadquery as cq

from cadforge.profile_recognition import recognize_coaxial_holes


def mesh_of(shape):
    vertices,faces=shape.tessellate(.04,.15)
    return trimesh.Trimesh(vertices=[v.toTuple() for v in vertices],faces=faces,process=True)


def plate(counterbore=False,blind=False):
    solid=cq.Workplane('XY').box(24,20,10,centered=(True,True,False)).val()
    bore=cq.Workplane('XY').circle(2).extrude(12 if not blind else 6).translate((0,0,-1 if not blind else 5)).val()
    solid=solid.cut(bore)
    if counterbore:
        solid=solid.cut(cq.Workplane('XY').circle(4).extrude(5).translate((0,0,6)).val())
    return mesh_of(solid)


def test_straight_through_hole_recognized_from_mesh():
    mesh=plate()
    features,indices=recognize_coaxial_holes(mesh)
    assert len(features)==1
    assert features[0]['center']==pytest.approx([0,0],abs=1e-7)
    assert features[0]['radius_mm']==pytest.approx(2,abs=1e-7)
    assert (features[0]['z_min'],features[0]['z_max'])==pytest.approx((0,10))
    expected=np.flatnonzero(np.linalg.norm(mesh.vertices[:,:2],axis=1)<=2+1e-7)
    assert np.array_equal(indices,expected)


def test_counterbore_includes_shoulder_and_every_profile_vertex():
    mesh=plate(counterbore=True)
    before=mesh.vertices.copy()
    features,indices=recognize_coaxial_holes(mesh)
    assert len(features)==1
    feature=features[0]
    assert feature['radius_mm']==pytest.approx(4,abs=1e-7)
    assert feature['profile']['minimum_radius_mm']==pytest.approx(2,abs=1e-7)
    assert feature['profile']['annular_shoulder_triangle_count']>0
    expected=np.flatnonzero(np.linalg.norm(mesh.vertices[:,:2],axis=1)<=4+1e-7)
    assert np.array_equal(indices,expected)
    assert np.array_equal(mesh.vertices,before), 'Recognition cannot mutate original coordinates'


def test_blind_channel_is_rejected():
    with pytest.raises(ValueError,match='blind|incomplete'):
        recognize_coaxial_holes(plate(blind=True))


def test_countersink_is_recognized_as_one_continuous_coaxial_profile():
    solid=cq.Workplane('XY').box(24,20,10,centered=(True,True,False)).val()
    bore=cq.Workplane('XY').circle(2).extrude(12).translate((0,0,-1)).val()
    cone=cq.Solid.makeCone(2,4,2,cq.Vector(0,0,8))
    mesh=mesh_of(solid.cut(bore.fuse(cone)))
    features,indices=recognize_coaxial_holes(mesh)
    assert len(features)==1
    assert features[0]['radius_mm']==pytest.approx(4,abs=1e-7)
    assert features[0]['profile']['minimum_radius_mm']==pytest.approx(2,abs=1e-7)
    rings=features[0]['profile']['rings']
    assert len(rings)>=3  # tessellator may subdivide the conical span
    assert all(r['radius_mm']==pytest.approx(2 if r['z']<=8 else r['z']-6,abs=1e-7) for r in rings)
    assert len(indices)>0


def test_slanted_and_non_circular_channels_are_rejected():
    tilted=plate();tilted.apply_transform(trimesh.transformations.rotation_matrix(np.deg2rad(12),[0,1,0]))
    with pytest.raises(ValueError):recognize_coaxial_holes(tilted)
    ellipse=plate();ellipse.apply_scale([1.3,1,1])
    with pytest.raises(ValueError):recognize_coaxial_holes(ellipse)


def test_public_plate_has_five_complete_profiles():
    path=Path(__file__).resolve().parents[1]/'artifacts/region-public/plate_holes.STL'
    if not path.exists():pytest.skip('Public development STL fixture has not been downloaded')
    mesh=trimesh.load(path,force='mesh',process=True)
    original=mesh.vertices.copy()
    features,indices=recognize_coaxial_holes(mesh)
    assert len(features)==5
    assert mesh.euler_number==2-2*len(features)
    assert len(indices)==384
    assert all(abs(f['z_min']-mesh.bounds[0,2])<1e-5 and abs(f['z_max']-mesh.bounds[1,2])<1e-5 for f in features)
    assert any(f['profile']['annular_shoulder_triangle_count']>0 for f in features)
    assert all(len(f['profile']['rings'])>=3 for f in features)
    assert np.array_equal(original,mesh.vertices)
