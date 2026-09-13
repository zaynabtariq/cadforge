"""Independent atomic composition tests; no frozen benchmark fixtures."""
from pathlib import Path
import numpy as np
import pytest
import trimesh
from cadforge.workspace import PythonWorkspace


@pytest.fixture
def composed_workspace(tmp_path):
    source = tmp_path / 'stock.stl'
    trimesh.creation.box(extents=[10,12,14]).export(source)
    store = tmp_path / 'production-learning.json'
    service = PythonWorkspace(tmp_path / 'workspace',region_learning_path=store)
    state = service.import_file(source)
    selection = {'part_id':state['parts'][0]['id']}
    return service,state,selection,store


def steps_for(selection):
    return [{'command':{'op':'translate','axis':'x','amount_mm':5},'selection':selection},
            {'command':{'op':'resize','axis':'y','target_mm':24},'selection':selection}]


def test_same_part_composed_preview_commit_once_and_undo_once(composed_workspace):
    service,state,selection,store = composed_workspace
    original = service.export_path(state['id']).read_bytes()
    preview = service.preview_sequence(state['id'],steps_for(selection),expected_revision=state['revision'])
    assert preview['accepted'], repr(preview)
    assert service.state(state['id']) == state
    assert service.export_path(state['id']).read_bytes() == original
    assert len(preview['parts']) == 1
    assert preview['parts'][0]['id'] == selection['part_id']
    mesh = trimesh.load(preview['parts'][0]['stl_path'],force='mesh')
    np.testing.assert_allclose(mesh.extents,[10,24,14])
    np.testing.assert_allclose(mesh.bounds.mean(axis=0),[5,0,0])
    assert mesh.is_watertight and mesh.volume > 0
    committed = service.commit(state['id'],preview['preview_id'])
    assert committed['revision'] == state['revision']+1
    assert committed['parent_version'] == state['version']
    assert committed['history'][-1]['command']['op'] == 'sequence'
    service.undo(state['id'])
    assert service.export_path(state['id']).read_bytes() == original
    assert not store.exists(), 'Speculative composition must not write production learning'


def test_failure_in_later_step_rolls_back_entire_chain(composed_workspace):
    service,state,selection,store = composed_workspace
    original = service.export_path(state['id']).read_bytes()
    steps = steps_for(selection)
    steps[1]['command']['target_mm'] = -1
    preview = service.preview_sequence(state['id'],steps)
    assert not preview['accepted'], repr(preview)
    assert any(not check['passed'] for check in preview['checks'])
    assert service.state(state['id']) == state
    assert service.export_path(state['id']).read_bytes() == original
    with pytest.raises(ValueError):service.commit(state['id'],preview['preview_id'])
    assert not store.exists()


def test_stale_sequence_revision_rejected_before_publishing(composed_workspace):
    service,state,selection,store = composed_workspace
    before = service.state(state['id'])
    with pytest.raises(ValueError):
        service.preview_sequence(state['id'],steps_for(selection),expected_revision=state['revision']+1)
    assert service.state(state['id']) == before


@pytest.mark.parametrize('kind',['too_many','nested'])
def test_invalid_sequence_shape_rejected_without_mutation(composed_workspace,kind):
    service,state,selection,store = composed_workspace
    steps = steps_for(selection)
    if kind == 'too_many':steps = [steps[0]]*9
    else:steps[1] = {'command':{'op':'sequence','steps':steps_for(selection)},'selection':selection}
    try:
        preview = service.preview_sequence(state['id'],steps)
    except ValueError:
        pass
    else:
        assert not preview['accepted'], repr(preview)
        with pytest.raises(ValueError):service.commit(state['id'],preview['preview_id'])
    assert service.state(state['id']) == state
    assert not store.exists()


@pytest.mark.parametrize('later_failure',[False,True])
def test_real_region_repair_in_sequence_never_updates_production_learning(tmp_path,later_failure):
    source = tmp_path / 'sphere.stl'
    trimesh.creation.icosphere(subdivisions=2,radius=10).export(source)
    store = tmp_path / 'production-learning.json'
    store.write_text('{"version":2,"evidence":[],"skills":[],"quarantines":[]}\n')
    before_store = store.read_bytes()
    service = PythonWorkspace(tmp_path / 'workspace',region_learning_path=store)
    state = service.import_file(source)
    part = state['parts'][0];lo,hi = part['bounds']
    region = {'part_id':part['id'],'region':{'min':[-1,lo[1]-1,lo[2]-1],'max':[hi[0]+1,hi[1]+1,hi[2]+1]}}
    steps = [{'command':{'op':'translate','axis':'y','amount_mm':7},'selection':region},
             {'command':({'op':'resize','axis':'x','target_mm':-1} if later_failure else {'op':'translate','axis':'x','amount_mm':1}),
              'selection':{'part_id':part['id']}}]
    original = service.export_path(state['id']).read_bytes()
    preview = service.preview_sequence(state['id'],steps)
    assert preview['accepted'] is (not later_failure), repr(preview)
    assert store.read_bytes() == before_store
    assert service.export_path(state['id']).read_bytes() == original
    assert service.state(state['id']) == state


def test_sequence_rollback_retains_counterexample_to_persistent_priority(tmp_path):
    from cadforge.edit_learning import recommend
    import json
    store=tmp_path/'learning.json'
    service=PythonWorkspace(tmp_path/'ws',region_learning_path=store)
    states=[]
    selections=[]
    for name,mesh,amount in [('sphere',trimesh.creation.icosphere(subdivisions=2,radius=10),7),
                              ('capsule',trimesh.creation.capsule(height=12,radius=8,count=[12,12]),5)]:
        source=tmp_path/(name+'.stl');mesh.export(source)
        state=service.import_file(source);states.append(state)
        part=state['parts'][0];lo,hi=part['bounds']
        selection={'part_id':part['id'],'region':{'min':[-1,lo[1]-1,lo[2]-1],'max':[hi[0]+1,hi[1]+1,hi[2]+1]}}
        selections.append(selection)
        assert service.preview(state['id'],{'op':'translate','axis':'y','amount_mm':amount},selection)['accepted']
    assert recommend({'op':'translate','axis':'y'},path=store)['skill_id']
    state=states[0];selection=selections[0]
    result=service.preview_sequence(state['id'],[
        {'command':{'op':'translate','axis':'y','amount_mm':100},'selection':selection},
        {'command':{'op':'translate','axis':'x','amount_mm':1},'selection':{'part_id':selection['part_id']}}])
    assert not result['accepted']
    assert service.state(state['id'])==state
    assert result['step_outcomes'][0]['persistent_learning']['status']=='quarantined'
    assert recommend({'op':'translate','axis':'y'},path=store)['skill_id'] is None
    saved=json.loads(store.read_text())
    assert len(saved['skills'])==1 and len(saved['evidence'])==3
    assert saved['evidence'][-1]['preview_id']==result['step_outcomes'][0]['retained_counterexample']['preview_id']
    assert len(saved['evidence'][-1]['preview_id'])==32
