"""Independent natural-language sequence intent and intermediate-state tests."""
import numpy as np
import pytest
import trimesh
from cadforge.workspace import PythonWorkspace
from cadforge.sequence_planner import plan_sequence


@pytest.fixture
def selected_box(tmp_path):
    source = tmp_path / 'box.stl'
    trimesh.creation.box(extents=[10,10,10]).export(source)
    service = PythonWorkspace(tmp_path / 'workspace',region_learning_path=tmp_path / 'learning.json')
    state = service.import_file(source)
    return service,state,{'part_id':state['parts'][0]['id']}


def plan(fixture,request,selection=None):
    service,state,default = fixture
    return plan_sequence(service,state['id'],request,default if selection is None else selection,state['revision'],use_model=False)


def test_relative_second_step_uses_actual_intermediate_extent(selected_box):
    service,state,selection = selected_box
    original = service.export_path(state['id']).read_bytes()
    result = plan(selected_box,'make this 1 cm wider then make this 1 cm wider')
    assert result['preview']['accepted'], result
    assert [step['command']['target_mm'] for step in result['preview']['step_outcomes']] == [20.,30.]
    mesh = trimesh.load(result['preview']['parts'][0]['stl_path'],force='mesh')
    np.testing.assert_allclose(mesh.extents,[30,10,10])
    assert service.export_path(state['id']).read_bytes() == original
    assert service.state(state['id']) == state
    assert result['usage']['model_requests'] == 0


@pytest.mark.parametrize('prompt',[
    'make this 1 cm wider then make this 100 mm narrower',
    'make this 1 cm wider then move this right',
])
def test_later_invalid_or_underspecified_clause_rolls_back(selected_box,prompt):
    service,state,selection = selected_box
    original = service.export_path(state['id']).read_bytes()
    result = plan(selected_box,prompt)
    preview = result['preview']
    assert not preview['accepted'], result
    assert preview['planning'][-1]['clarification']
    assert service.state(state['id']) == state
    assert service.export_path(state['id']).read_bytes() == original
    with pytest.raises(ValueError):service.commit(state['id'],preview['preview_id'])


@pytest.mark.parametrize('reference',[
    {'point':[0,0,5]},
    {'region':{'min':[0,0,0],'max':[5,5,5]}},
])
def test_surface_or_region_reference_requires_explicit_sequence_contract(selected_box,reference):
    service,state,selection = selected_box
    result = plan(selected_box,'move this 1 mm right then make this 1 cm wider',selection|reference)
    assert result['command'] is None and result['clarification']
    assert 'preview' not in result
    assert service.state(state['id']) == state


@pytest.mark.parametrize('constraint',[
    'and preserve holes','without changing the holes','and keep pivot geometry fixed',
])
def test_global_preservation_not_silently_scoped_to_one_clause(selected_box,constraint):
    result = plan(selected_box,'make this 1 cm wider then move this 2 mm right '+constraint)
    assert result['command'] is None and result['clarification']
    assert 'preview' not in result


def test_single_edit_not_intercepted_by_sequence_planner(selected_box):
    service,state,selection = selected_box
    assert plan(selected_box,'make this 1 cm wider') is None
    assert service.state(state['id']) == state
