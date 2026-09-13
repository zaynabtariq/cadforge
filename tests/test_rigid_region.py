"""Independent exact rigid-region intent versus explicitly permitted transition."""
from pathlib import Path
import numpy as np
import pytest
import trimesh
from cadforge.workspace import PythonWorkspace


@pytest.fixture
def region_workspace(tmp_path):
    source = tmp_path / 'sphere.stl'
    trimesh.creation.icosphere(subdivisions=2,radius=10).export(source)
    service = PythonWorkspace(tmp_path / 'workspace',region_learning_path=tmp_path / 'learning.json')
    state = service.import_file(source)
    lo,hi = state['parts'][0]['bounds']
    selection = {'part_id':state['parts'][0]['id'],
                 'region':{'min':[-1,lo[1]-1,lo[2]-1],'max':[hi[0]+1,hi[1]+1,hi[2]+1]}}
    return service,state,selection


def test_rigid_mode_rejects_actual_case_that_default_transition_repairs(region_workspace):
    service,state,selection = region_workspace
    original = service.export_path(state['id']).read_bytes()
    command = {'op':'translate','axis':'y','amount_mm':7.}
    default = service.preview(state['id'],command,selection)
    assert default['accepted'], default
    assert default['learning']['attempts'] == 2
    rigid = service.preview(state['id'],command|{'translation_mode':'rigid'},selection)
    assert not rigid['accepted'], repr(rigid)
    assert len(rigid['repair_trials']) == 1
    assert rigid['repair_trials'][0]['strategy'] == 'sharp'
    assert not rigid['repair_trials'][0]['accepted']
    assert service.export_path(state['id']).read_bytes() == original
    assert service.state(state['id']) == state
    with pytest.raises(ValueError):service.commit(state['id'],rigid['preview_id'])


def test_small_rigid_move_preserves_requested_vector_and_outside_coordinates(region_workspace):
    service,state,selection = region_workspace
    source = trimesh.load(state['parts'][0]['stl_path'],force='mesh')
    command = {'op':'translate','axis':'y','amount_mm':.1,'translation_mode':'rigid'}
    preview = service.preview(state['id'],command,selection)
    assert preview['accepted'], repr(preview)
    candidate = trimesh.load(preview['parts'][0]['stl_path'],force='mesh')
    lo = np.asarray(selection['region']['min']); hi = np.asarray(selection['region']['max'])
    selected = np.all((source.vertices>=lo)&(source.vertices<=hi),axis=1)
    assert selected.any() and (~selected).any()
    expected = source.vertices.copy();expected[selected,1] += .1
    # Binary STL quantizes coordinates to float32. Compare every expected vertex
    # exactly after this known serialization, independently of backend checks.
    expected = expected.astype(np.float32).astype(np.float64)
    assert set(map(tuple,candidate.vertices)) == set(map(tuple,expected))
    assert all(tuple(v) in set(map(tuple,candidate.vertices)) for v in source.vertices[~selected])
    assert candidate.is_watertight and candidate.is_winding_consistent and candidate.volume > 0


@pytest.mark.parametrize('mode',['soft','',None,1,{'rigid':True}])
def test_malformed_translation_mode_rejected_without_mutation(region_workspace,mode):
    service,state,selection = region_workspace
    original = service.export_path(state['id']).read_bytes()
    preview = service.preview(state['id'],{'op':'translate','axis':'y','amount_mm':.1,'translation_mode':mode},selection)
    assert not preview['accepted'], repr(preview)
    assert service.export_path(state['id']).read_bytes() == original
    assert service.state(state['id']) == state


def test_learned_priority_or_command_hint_cannot_bypass_rigid_constraint(region_workspace,monkeypatch):
    from cadforge import edit_learning
    service,state,selection = region_workspace
    monkeypatch.setattr(edit_learning,'recommend',lambda *args,**kwargs:{
        'strategy':'interior_transition_power_1','skill_id':'adversarial-priority','context':edit_learning.validator_context()})
    result = service.preview(state['id'],{'op':'translate','axis':'y','amount_mm':7.,
        'translation_mode':'rigid','learned_strategy':'interior_transition_power_1'},selection)
    assert not result['accepted'], repr(result)
    assert len(result['repair_trials']) == 1
    assert result['repair_trials'][0]['strategy'] == 'sharp'
    assert service.state(state['id']) == state
