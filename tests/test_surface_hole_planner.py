"""Independent intent checks for entry-anchored drilling on selected faces."""
import math

import pytest

from cadforge.edit_planner import plan_edit


STATE = {'parts': [{'id': 'surface-part', 'bounds': [[-10., -10., 0.], [10., 10., 10.]]}]}
REQUEST = 'drill a 4 mm diameter hole 3 mm deep here'


def selected(point, normal):
    return {'part_id': 'surface-part', 'point': point, 'normal': normal}


@pytest.mark.parametrize('point,normal', [
    ([10., 2., 5.], [1., 0., 0.]),
    ([-10., 2., 5.], [-1., 0., 0.]),
    ([3., 2., 5.], [math.cos(math.radians(37)), 0., math.sin(math.radians(37))]),
])
@pytest.mark.parametrize('prompt', [REQUEST, 'drill a 0.4 cm diameter hole 0.3 cm deep here'])
def test_surface_drill_preserves_entry_normal_and_converts_dimensions(point, normal, prompt):
    result = plan_edit(prompt, selected(point, normal), STATE, use_model=False)
    command = result['command']
    assert result['clarification'] is None, result
    assert command['op'] == 'drill_surface_hole'
    assert command['radius_mm'] == 2.
    assert command['depth_mm'] == 3.
    assert command['entry'] == point
    assert command['normal'] == pytest.approx(normal, abs=1e-12)


def test_side_face_without_normal_requires_clarification():
    result = plan_edit(REQUEST, {'part_id': 'surface-part', 'point': [10., 2., 5.]}, STATE, use_model=False)
    assert result['command'] is None
    assert result['clarification']


@pytest.mark.parametrize('prompt', [
    'put a 4 mm hole here',
    'drill a 4 mm through hole here',
])
def test_side_face_without_blind_depth_cannot_fall_back_to_z_through_cut(prompt):
    result = plan_edit(prompt, selected([10., 2., 5.], [1., 0., 0.]), STATE, use_model=False)
    assert result['command'] is None, result
    assert result['clarification']


@pytest.mark.parametrize('prompt', [
    'drill a 4 mm hole 3 mm deep along z',
    'drill a 4 mm hole 3 mm deep angled 45 degrees',
])
def test_explicit_orientation_is_not_discarded_for_selected_normal(prompt):
    result = plan_edit(prompt, selected([10., 2., 5.], [1., 0., 0.]), STATE, use_model=False)
    assert result['command'] is None, result
    assert result['clarification']


@pytest.mark.parametrize('normal', [[0., 0., 0.], [float('nan'), 0., 0.], [0., float('inf'), 0.], [0., 0., -float('inf')]])
def test_invalid_selected_normals_fail_before_planning(normal):
    with pytest.raises(ValueError):
        plan_edit(REQUEST, selected([10., 2., 5.], normal), STATE, use_model=False)


def test_model_centered_cut_cannot_replace_actual_surface_entry_and_normal():
    from pydantic_ai.models.test import TestModel
    normal = [math.cos(math.radians(37)), 0., math.sin(math.radians(37))]
    point = [3., 2., 5.]
    model = TestModel(custom_output_args={
        'command': {'op': 'cut_cylinder', 'radius_mm': 2., 'height_mm': 3., 'center': [0., 0., 0.]},
        'explanation': 'Use a centered cylinder instead of the selected face.', 'clarification': None,
    })
    result = plan_edit(REQUEST, selected(point, normal), STATE, use_model=True, model=model)
    assert result['command']['op'] == 'drill_surface_hole', result
    assert result['command']['entry'] == point
    assert result['command']['normal'] == pytest.approx(normal, abs=1e-12)
    assert result['command']['radius_mm'] == 2.
    assert result['command']['depth_mm'] == 3.
    assert result['usage']['model_requests'] == 1
    assert result['planner'] == 'pydantic_ai_with_numeric_guard'


@pytest.mark.parametrize('point,normal,direction', [
    ([1., 2., 10.], [0., 0., 1.], -1),
    ([1., 2., 0.], [0., 0., -1.], 1),
])
def test_z_extreme_faces_keep_existing_blind_drilling_operation(point, normal, direction):
    result = plan_edit(REQUEST, selected(point, normal), STATE, use_model=False)
    assert result['command'] == {'op': 'drill_blind_hole', 'radius_mm': 2., 'depth_mm': 3.,
                                 'entry': point, 'direction': direction}, result
