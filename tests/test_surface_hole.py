"""Independent world-space surface drilling tests; source fixtures are public dev geometry."""
import math
import numpy as np
import pytest
import trimesh
from cadforge.workspace import PythonWorkspace


def workspace_for(tmp_path, mesh):
    source = tmp_path / 'surface_stock.stl'
    mesh.export(source)
    service = PythonWorkspace(tmp_path / 'workspace')
    state = service.import_file(source)
    assert len(state['parts']) == 1
    return service, state, {'part_id':state['parts'][0]['id']}


def rotation():
    transform = trimesh.transformations.rotation_matrix(np.deg2rad(37.),[1.,2.,3.])
    transform[:3,3] = [11.,-7.,4.]
    return transform


def command(entry, normal, depth=3.):
    return {'op':'drill_surface_hole','radius_mm':2.,'depth_mm':depth,
            'entry':np.asarray(entry).tolist(),'normal':np.asarray(normal).tolist()}


@pytest.mark.parametrize('axis,sign',[(0,-1),(0,1),(1,-1),(1,1),(2,-1),(2,1)])
@pytest.mark.parametrize('rotated',[False,True])
def test_six_faces_and_rigid_transform_depth_volume_and_exact_undo(tmp_path,axis,sign,rotated):
    mesh = trimesh.creation.box(extents=[20.,20.,20.])
    normal = np.eye(3)[axis] * sign
    entry = normal * 10.
    if rotated:
        transform = rotation(); mesh.apply_transform(transform)
        entry = transform[:3,:3] @ entry + transform[:3,3]
        normal = transform[:3,:3] @ normal
    service,state,selection = workspace_for(tmp_path,mesh)
    original_bytes = service.export_path(state['id']).read_bytes()
    source = trimesh.load(state['parts'][0]['stl_path'],force='mesh')
    preview = service.preview(state['id'],command(entry,normal),selection)
    assert preview['accepted'], repr(preview)
    candidate = trimesh.load(preview['parts'][0]['stl_path'],force='mesh')
    candidate_coordinates = set(map(tuple,candidate.vertices))
    assert all(tuple(vertex) in candidate_coordinates for vertex in source.vertices), 'Drilling away from corners must preserve every original stock corner exactly'
    relative = candidate.vertices-entry
    axial = relative @ normal
    radial = np.linalg.norm(relative-axial[:,None]*normal,axis=1)
    bore = radial <= 2.00002
    assert bore.sum() >= 64
    assert axial[bore].min() == pytest.approx(-3.,abs=2e-5)
    assert axial[bore].max() == pytest.approx(0.,abs=2e-5)
    expected_removed = 32 * 4 * math.sin(2*math.pi/64) * 3
    assert source.volume-candidate.volume == pytest.approx(expected_removed,rel=5e-6)
    assert candidate.is_watertight and candidate.is_winding_consistent and candidate.volume > 0
    assert service.export_path(state['id']).read_bytes() == original_bytes
    service.commit(state['id'],preview['preview_id'])
    committed = trimesh.load(service.export_path(state['id']),force='mesh')
    assert committed.volume == pytest.approx(candidate.volume,abs=1e-8)
    service.undo(state['id'])
    assert service.export_path(state['id']).read_bytes() == original_bytes


@pytest.mark.parametrize('entry,normal,depth',[
    ([0,0,10],[0,0,0],3),
    ([0,0,10],[float('nan'),0,1],3),
    ([0,0,10],[0,0,float('inf')],3),
    ([0,0,0],[0,0,1],3),
    ([0,0,11],[0,0,1],3),
    ([0,0,10],[0,0,-1],3),
    ([0,0,10],[2**-.5,0,2**-.5],3),
    ([0,0,10],[0,0,1],20),
])
def test_invalid_surface_contract_rejects_without_mutation(tmp_path,entry,normal,depth):
    service,state,selection = workspace_for(tmp_path,trimesh.creation.box(extents=[20,20,20]))
    original = service.export_path(state['id']).read_bytes()
    if not np.isfinite(normal).all():
        with pytest.raises(ValueError):
            service.preview(state['id'],command(entry,normal,depth),selection)
        assert service.state(state['id']) == state
        assert service.export_path(state['id']).read_bytes() == original
        return
    preview = service.preview(state['id'],command(entry,normal,depth),selection)
    assert not preview['accepted'], repr(preview)
    assert any(not check['passed'] for check in preview['checks'])
    assert service.state(state['id']) == state
    assert service.export_path(state['id']).read_bytes() == original
    with pytest.raises(ValueError):service.commit(state['id'],preview['preview_id'])


def test_rotated_tiny_through_void_cannot_be_certified_as_blind_floor(tmp_path):
    mesh = trimesh.boolean.difference([
        trimesh.creation.box(extents=[20,20,10]),
        trimesh.creation.cylinder(radius=.003,height=12,sections=32),
    ],engine='manifold')
    transform = rotation(); mesh.apply_transform(transform)
    entry = transform[:3,:3] @ np.array([0.,0.,5.]) + transform[:3,3]
    normal = transform[:3,:3] @ np.array([0.,0.,1.])
    service,state,selection = workspace_for(tmp_path,mesh)
    original = service.export_path(state['id']).read_bytes()
    preview = service.preview(state['id'],command(entry,normal),selection)
    assert not preview['accepted'], repr(preview)
    assert any(not check['passed'] for check in preview['checks'])
    assert service.export_path(state['id']).read_bytes() == original
    with pytest.raises(ValueError):service.commit(state['id'],preview['preview_id'])
