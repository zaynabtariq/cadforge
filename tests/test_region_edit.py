import numpy as np
import pytest
import trimesh
from cadforge.region_edit import deform_region,RegionEditError


def test_cube_partial_translation_preserves_opposite_half():
    mesh=trimesh.creation.box(extents=[20,10,10])
    region={'min':[0,-6,-6],'max':[11,6,6]}
    result,checks=deform_region(mesh,{'op':'translate','axis':'x','amount_mm':20},region)
    assert np.array_equal(result.vertices[mesh.vertices[:,0]<0],mesh.vertices[mesh.vertices[:,0]<0])
    assert np.allclose(result.vertices[mesh.vertices[:,0]>0,0],30)
    assert all(c['passed'] for c in checks)


def test_fresh_sphere_local_edit_and_outside_invariance():
    mesh=trimesh.creation.icosphere(subdivisions=2,radius=10)
    region={'min':[0,-11,-11],'max':[11,11,11]}
    result,checks=deform_region(mesh,{'op':'translate','axis':'x','amount_mm':2},region)
    assert np.array_equal(result.vertices[mesh.vertices[:,0]<0],mesh.vertices[mesh.vertices[:,0]<0])
    assert result.is_watertight


def test_all_selected_resize_keeps_face_indices():
    mesh=trimesh.creation.box(extents=[10,10,10])
    result,checks=deform_region(mesh,{'op':'resize','axis':'y','target_mm':20},{'min':[-6,-6,-6],'max':[6,6,6]})
    assert result.extents[1]==pytest.approx(20)
    assert np.array_equal(mesh.faces,result.faces)


def test_inversion_is_rejected_without_mutating_input():
    mesh=trimesh.creation.box(extents=[20,10,10]);original=mesh.vertices.copy()
    with pytest.raises(RegionEditError) as failure:
        deform_region(mesh,{'op':'translate','axis':'x','amount_mm':-30},{'min':[0,-6,-6],'max':[11,6,6]})
    assert failure.value.trials
    assert np.array_equal(mesh.vertices,original)


def test_empty_selection_rejected():
    with pytest.raises(RegionEditError,match='no mesh vertices'):
        deform_region(trimesh.creation.box(),{'op':'move','axis':'x','amount_mm':2},{'min':[4,4,4],'max':[5,5,5]})


def test_intersecting_input_rejected():
    a=trimesh.creation.box(extents=[10,10,10]);b=a.copy();b.apply_translation([3,3,3])
    overlapping=trimesh.util.concatenate([a,b])
    with pytest.raises(RegionEditError,match='intersecting'):
        deform_region(overlapping,{'op':'move','axis':'x','amount_mm':1},{'min':[-20]*3,'max':[20]*3})


def test_actual_failure_correction_transfer_and_persistent_reuse(tmp_path):
    import json
    from cadforge.region_edit import record_validated_transfer
    sphere=trimesh.creation.icosphere(subdivisions=2,radius=10)
    capsule=trimesh.creation.capsule(height=12,radius=8,count=[12,12])
    path=tmp_path/'learned-regions.json'
    for mesh,amount in [(sphere,7),(capsule,5)]:
        lo,hi=mesh.bounds
        region={'min':[-1,float(lo[1]-1),float(lo[2]-1)],'max':[float(hi[0]+1),float(hi[1]+1),float(hi[2]+1)]}
        _,checks,state=record_validated_transfer(path,mesh,{'op':'move','axis':'y','amount_mm':amount},region)
        trials=next(c['detail'] for c in checks if c['name']=='repair_trials')
        assert not trials[0]['accepted'] and trials[-1]['accepted']
        json.dumps(checks) # complete trace must be serializable
    persisted=json.loads(path.read_text())
    assert persisted['skills'][0]['validated_mesh_count']==2
    fresh=trimesh.creation.capsule(height=15,radius=9,count=[12,12])
    lo,hi=fresh.bounds
    _,checks=deform_region(fresh,{'op':'move','axis':'y','amount_mm':5,'learned_strategy':persisted['skills'][0]['strategy']},{'min':[-1,float(lo[1]-1),float(lo[2]-1)],'max':[float(hi[0]+1),float(hi[1]+1),float(hi[2]+1)]})
    trials=next(c['detail'] for c in checks if c['name']=='repair_trials')
    assert trials[0]['accepted'] and trials[0]['strategy']=='interior_transition_power_1'
