"""Independent preservation contracts across every speculative sequence step."""
import numpy as np
import pytest
import trimesh
from cadforge.workspace import PythonWorkspace


@pytest.fixture
def perforated_workspace(tmp_path):
    box = trimesh.creation.box(extents=[60,30,4])
    cutters=[]
    for x in [-12,12]:
        hole=trimesh.creation.cylinder(radius=3,height=10,sections=48)
        hole.apply_translation([x,0,0]);cutters.append(hole)
    mesh=trimesh.boolean.difference([box,*cutters],engine='manifold')
    source=tmp_path/'perforated.stl';mesh.export(source)
    service=PythonWorkspace(tmp_path/'workspace',region_learning_path=tmp_path/'learning.json')
    state=service.import_file(source);part=state['parts'][0]
    return service,state,{'part_id':part['id']},[{'kind':'preserve_holes','part_id':part['id']}]


def protected_steps(selection):
    return [{'command':{'op':'resize_preserving_holes','axis':'x','target_mm':80},'selection':selection},
            {'command':{'op':'resize_preserving_holes','axis':'y','target_mm':50},'selection':selection}]


def test_two_protected_resizes_retain_measured_original_bore_vertices(perforated_workspace):
    service,state,selection,invariants=perforated_workspace
    original=trimesh.load(state['parts'][0]['stl_path'],force='mesh')
    baseline=service.export_path(state['id']).read_bytes()
    preview=service.preview_sequence(state['id'],protected_steps(selection),invariants=invariants)
    assert preview['accepted'],repr(preview)
    result=trimesh.load(preview['parts'][0]['stl_path'],force='mesh')
    np.testing.assert_allclose(result.extents,[80,50,4],atol=1e-5)
    coordinates=set(map(tuple,result.vertices))
    for x in [-12,12]:
        radial=np.linalg.norm(original.vertices[:,:2]-[x,0],axis=1)
        bore=original.vertices[np.abs(radial-3)<2e-5]
        assert len(bore)>=48
        assert all(tuple(v) in coordinates for v in bore)
    assert len(preview['step_outcomes'])==2
    for step in preview['step_outcomes']:
        assert any(c['name']=='invariant.preserve_holes' and c['passed'] for c in step['checks'])
    assert service.export_path(state['id']).read_bytes()==baseline
    service.commit(state['id'],preview['preview_id'])
    service.undo(state['id'])
    assert service.export_path(state['id']).read_bytes()==baseline


@pytest.mark.parametrize('restore_later',[False,True])
def test_hole_motion_rejected_at_first_violating_step_even_if_later_restored(perforated_workspace,restore_later):
    service,state,selection,invariants=perforated_workspace
    baseline=service.export_path(state['id']).read_bytes()
    move={'command':{'op':'translate','axis':'x','amount_mm':1},'selection':selection}
    if restore_later:
        steps=[move,{'command':{'op':'translate','axis':'x','amount_mm':-1},'selection':selection}]
        expected_steps=1
    else:
        steps=[protected_steps(selection)[0],move]
        expected_steps=2
    preview=service.preview_sequence(state['id'],steps,invariants=invariants)
    assert not preview['accepted'],repr(preview)
    assert len(preview['step_outcomes'])==expected_steps
    assert any(c['name']=='invariant.preserve_holes' and not c['passed'] for c in preview['step_outcomes'][-1]['checks'])
    assert service.export_path(state['id']).read_bytes()==baseline
    assert service.state(state['id'])==state
    with pytest.raises(ValueError):service.commit(state['id'],preview['preview_id'])


@pytest.mark.parametrize('bad',[
    {},[{}],[{'kind':'unknown','part_id':'f'*32}],
    [{'kind':'preserve_holes','part_id':'f'*32}],
    [{'kind':'preserve_holes','part_id':'f'*32,'ignore_failure':True}],
])
def test_malformed_or_unknown_invariant_rejected_before_mutation(perforated_workspace,bad):
    service,state,selection,invariants=perforated_workspace
    baseline=service.export_path(state['id']).read_bytes()
    with pytest.raises(ValueError):
        service.preview_sequence(state['id'],protected_steps(selection),invariants=bad)
    assert service.state(state['id'])==state
    assert service.export_path(state['id']).read_bytes()==baseline


def test_plain_language_compiles_global_hole_contract(perforated_workspace):
    from cadforge.sequence_planner import plan_sequence
    service,state,selection,_=perforated_workspace
    result=plan_sequence(service,state['id'],'Make this 1 cm wider then make this 1 cm wider, keeping holes fixed throughout',selection,0,use_model=False)
    pv=result['preview'];assert pv['accepted'],pv
    assert len(pv['invariants'])==1
    assert [s['command']['op'] for s in pv['step_outcomes']]==['resize_preserving_holes']*2
    assert [s['command']['target_mm'] for s in pv['step_outcomes']]==[70,80]
    assert pv['step_outcomes'][1]['input_parts'][0]['bounds'][1][0]-pv['step_outcomes'][1]['input_parts'][0]['bounds'][0][0]==70


def test_plain_language_later_translation_cannot_drop_contract(perforated_workspace):
    from cadforge.sequence_planner import plan_sequence
    service,state,selection,_=perforated_workspace
    result=plan_sequence(service,state['id'],'Make this 1 cm wider then move this 1 mm right, keeping holes fixed throughout',selection,0,use_model=False)
    assert not result['preview']['accepted']
    assert not result['preview']['step_outcomes'][1]['accepted']
    assert service.state(state['id'])==state


def test_unrecognized_extra_constraint_still_clarifies(perforated_workspace):
    from cadforge.sequence_planner import plan_sequence
    service,state,selection,_=perforated_workspace
    result=plan_sequence(service,state['id'],'Make this 1 cm wider then move this 1 mm right without changing lever length, keeping holes fixed throughout',selection,0,use_model=False)
    assert result['clarification'] and result['command'] is None


@pytest.mark.parametrize('condition',[
    'not keeping holes fixed throughout',
    'never keeping holes fixed throughout',
    'without keeping holes fixed throughout',
    "don't keep holes fixed throughout",
    'rather than keeping holes fixed throughout',
    'keeping holes fixed throughout except the left hole',
    'keeping holes fixed throughout and no other changes',
])
def test_qualified_preservation_never_silently_becomes_positive(perforated_workspace,monkeypatch,condition):
    from cadforge import sequence_planner
    service,state,selection,_=perforated_workspace
    def unexpected(*args,**kwargs):
        pytest.fail('Ambiguous shared constraint reached CAD execution')
    monkeypatch.setattr(sequence_planner,'preview_sequence',unexpected)
    result=sequence_planner.plan_sequence(service,state['id'],
        'Make this 1 cm wider then make this 1 cm wider, '+condition,selection,0,use_model=False)
    assert result['clarification'] and result['command'] is None
    assert result['usage']['model_requests']==0
    assert service.state(state['id'])==state


@pytest.mark.parametrize('violate',[False,True])
def test_rotated_hole_contract_checks_every_step(perforated_workspace,tmp_path,violate):
    from cadforge.composition_invariants import hole_signature
    service,state,_,_=perforated_workspace
    mesh=trimesh.load(state['parts'][0]['stl_path'],force='mesh')
    mesh.vertices=np.asarray(mesh.vertices)[:,[0,2,1]]*np.array([1,-1,1])
    source=tmp_path/'rotated.stl';mesh.export(source)
    rotated=service.import_file(source);part=rotated['parts'][0]
    selection={'part_id':part['id']};contracts=[{'kind':'preserve_holes','part_id':part['id']}]
    baseline=service.export_path(rotated['id']).read_bytes()
    signature=hole_signature(part['stl_path'])
    steps=[{'selection':selection,'command':{'op':'resize_preserving_holes','axis':'x','target_mm':80}},
           {'selection':selection,'command':{'op':'translate','axis':'x','amount_mm':1} if violate else {'op':'resize_preserving_holes','axis':'x','target_mm':100}}]
    result=service.preview_sequence(rotated['id'],steps,invariants=contracts)
    assert result['accepted'] is not violate
    assert service.export_path(rotated['id']).read_bytes()==baseline
    assert result['step_outcomes'][0]['accepted']
    if violate:
        assert any(c['name']=='invariant.preserve_holes' and not c['passed'] for c in result['step_outcomes'][1]['checks'])
        with pytest.raises(ValueError):service.commit(rotated['id'],result['preview_id'])
    else:
        assert hole_signature(result['parts'][0]['stl_path'])==signature
        service.commit(rotated['id'],result['preview_id']);service.undo(rotated['id'])
        assert service.export_path(rotated['id']).read_bytes()==baseline
