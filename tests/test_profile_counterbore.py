"""Public profile counterbore contracts independent of fitted candidate claims."""
from pathlib import Path
import math
import numpy as np
import pytest
import trimesh
from cadforge.profile_counterbore import counterbore,CounterboreError
from cadforge.protected_edit import _recognized

PUBLIC=Path(__file__).resolve().parents[1]/'artifacts/region-public/plate_holes.STL'


@pytest.fixture(scope='module')
def public():return trimesh.load(PUBLIC,force='mesh',process=True)


@pytest.mark.parametrize('direction',[-1])
def test_public_center_cylindrical_entrance_preserves_all_other_profiles(public,direction):
    mesh=public.copy();features,indices=_recognized(mesh)
    center=[101.5999984741211,154.48073817441445]
    plane=float(mesh.bounds[1 if direction==-1 else 0,2]);entry=[*center,plane]
    result,checks,feature=counterbore(mesh,7.5,2,entry,direction)
    assert all(c['passed'] for c in checks)
    assert feature['kind']=='profile_counterbore'
    assert result.is_watertight and result.euler_number==mesh.euler_number
    bottom=plane+direction*2
    # External selection uses known center and conservative radial region, not
    # the operation's protected-index list. Every other bore vertex must survive.
    original=mesh.vertices[indices]
    unchanged=(np.linalg.norm(original[:,:2]-center,axis=1)>10)|((original[:,2]-bottom)*direction>1e-6)
    result_set={tuple(v) for v in result.vertices}
    assert all(tuple(v) in result_set for v in original[unchanged])
    floor=np.all(np.abs(result.triangles[:,:,2]-bottom)<1e-6,axis=1)&(np.linalg.norm(result.triangles_center[:,:2]-center,axis=1)<7.50001)
    assert floor.any() and result.area_faces[floor].sum()>0
    assert mesh.volume-result.volume==pytest.approx(result.area_faces[floor].sum()*2,rel=5e-6)
    assert np.array_equal(mesh.vertices,public.vertices)


@pytest.mark.parametrize('depth',[6.35,7.,12.7])
def test_crossing_old_shoulder_rejected(public,depth):
    with pytest.raises(CounterboreError):counterbore(public,7.5,depth,[101.5999984741211,154.48073817441445,public.bounds[1,2]])


def test_actual_public_tapered_entrances_rejected(public):
    features,_=_recognized(public)
    for f in features:
        if abs(f['center'][0]-101.6)<1:continue
        with pytest.raises(CounterboreError,match='cylindrical entrance'):counterbore(public,8,2,[*f['center'],public.bounds[1,2]])


def test_offaxis_and_undersize_rejected(public):
    for radius,entry in [(7.5,[101.7,154.48,public.bounds[1,2]]),(5,[101.5999984741211,154.48073817441445,public.bounds[1,2]])]:
        with pytest.raises(CounterboreError):counterbore(public,radius,2,entry)


def test_public_composition_failure_and_set_repair_are_recorded(public):
    _,checks,feature=counterbore(public,7.5,2,[101.5999984741211,154.48073817441445,public.bounds[1,2]])
    repair=feature['protected_void_repair']
    assert repair['post_restore_intersection_faces']>0
    assert repair['post_restore_added_faces']>0
    assert next(c['detail']['faces'] for c in checks if c['name'].endswith('original_bore_open'))==0
    assert next(c['detail']['added_faces'] for c in checks if c['name'].endswith('outside_stock_preserved'))==0


def test_known_public_bottom_precision_failure_is_rejected_without_mutation(public):
    before=public.vertices.copy()
    with pytest.raises(CounterboreError) as error:
        counterbore(public,7.5,2,[101.5999984741211,154.48073817441445,0],1)
    assert any(not c['passed'] for c in error.value.checks if c['name'].endswith(('original_bore_open','outside_stock_preserved')))
    assert np.array_equal(public.vertices,before)
