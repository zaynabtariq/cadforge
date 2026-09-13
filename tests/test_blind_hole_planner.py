"""Independent surface-anchored blind drilling intent regressions."""
import pytest
from cadforge.edit_planner import plan_edit

STATE = {'parts':[{'id':'part-1','bounds':[[-10.,-10.,0.],[10.,10.,10.]]}]}
TOP = {'part_id':'part-1','point':[1.,2.,10.]}
BOTTOM = {'part_id':'part-1','point':[1.,2.,0.]}


@pytest.mark.parametrize('prompt,radius,depth', [
    ('drill a 4 mm diameter hole 3 mm deep here',2.,3.),
    ('drill a 4mm hole 3mm deep here',2.,3.),
    ('drill a 0.4 cm diameter hole 0.3 cm deep here',2.,3.),
])
@pytest.mark.parametrize('selection,direction',[(TOP,-1),(BOTTOM,1)])
def test_blind_drilling_uses_surface_entry_inward_direction_and_units(prompt,radius,depth,selection,direction):
    result = plan_edit(prompt,selection,STATE,use_model=False)
    assert result['command'] == {'op':'drill_blind_hole','radius_mm':radius,'depth_mm':depth,
                                 'entry':selection['point'],'direction':direction}, result


@pytest.mark.parametrize('prompt,selection', [
    ('drill a 4 mm hole 3 mm deep here',{'part_id':'part-1','point':[10.,2.,5.]}),
    ('drill a 4 mm hole 10 mm deep here',TOP),
    ('drill a 4 mm hole 11 mm deep here',TOP),
    ('drill a 4 mm blind hole here',TOP),
    ('drill a 4 mm through hole 3 mm deep here',TOP),
])
def test_unsupported_or_contradictory_blind_drill_requires_clarification(prompt,selection):
    result = plan_edit(prompt,selection,STATE,use_model=False)
    assert result['command'] is None, result
    assert result['clarification']


def test_model_cannot_replace_surface_entry_blind_drill_with_centered_cut():
    from pydantic_ai.models.test import TestModel
    model = TestModel(custom_output_args={'command':{'op':'cut_cylinder','radius_mm':2.,'height_mm':3.,'center':TOP['point']},
                                         'explanation':'Centered cutting cylinder.', 'clarification':None})
    result = plan_edit('drill a 4 mm diameter hole 3 mm deep here',TOP,STATE,use_model=True,model=model)
    assert result['command'] == {'op':'drill_blind_hole','radius_mm':2.,'depth_mm':3.,'entry':TOP['point'],'direction':-1}, result


def test_explicit_centered_cylinder_retains_existing_center_semantics():
    result = plan_edit('add a cylinder radius 2 mm height 3 mm centered here',TOP,STATE,use_model=False)
    assert result['command'] == {'op':'add_cylinder','radius_mm':2.,'height_mm':3.,'center':TOP['point']}, result
