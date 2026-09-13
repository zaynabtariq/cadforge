import math
import pytest
from pydantic import ValidationError

from cadforge.edit_planner import Bounds, Cylinder, Resize, ResizePreservingHoles, plan_edit


SELECTION={"part_id":"part-1","point":[0.,0.,5.]}
STATE={"parts":[{"id":"part-1","bounds":[[-10.,-5.,0.],[10.,5.,10.]]}]}


@pytest.mark.parametrize("prompt,command", [
    ("make this 2 cm wider", {"op":"resize","axis":"x","target_mm":40.}),
    ("move this 3cm to the right", {"op":"translate","axis":"x","amount_mm":30.}),
    ("move this 1 inch left", {"op":"translate","axis":"x","amount_mm":-25.4}),
    ("make this 15 mm wide", {"op":"resize","axis":"x","target_mm":15.}),
    ("add a 10 x 20 x 30 mm box here", {"op":"add_box","size":[10.,20.,30.],"center":[0.,0.,5.]}),
    ("put a 5 mm hole here", {"op":"cut_cylinder","radius_mm":2.5,"height_mm":12.,"center":[0.,0.,5.]}),
    ("add a cylinder radius 2 mm height 10 mm here", {"op":"add_cylinder","radius_mm":2.,"height_mm":10.,"center":[0.,0.,5.]}),
])
def test_explicit_offline_units_and_relative_extents(prompt,command):
    result=plan_edit(prompt,SELECTION,STATE,use_model=False)
    assert result["command"]==command
    assert result["planner"]=="offline_parser"
    assert result["usage"]["model_requests"]==0


@pytest.mark.parametrize("prompt", [
    "move this 3cm away", "make this 2 cm wider but preserve pivot geometry",
    "add a 10mm tall cylinder here", "move this -3 cm right",
    "make this 30 mm narrower",
    "move this 3 cm right and make it 2 cm wider",
])
def test_ambiguity_and_invariants_are_not_silently_downgraded(prompt):
    result=plan_edit(prompt,SELECTION,STATE,use_model=False)
    assert result["command"] is None
    assert result["clarification"]


def test_region_bounds_use_selected_extent_and_addition_is_blocked():
    selected=SELECTION|{"region":{"min":[0.,0.,0.],"max":[5.,5.,5.]}}
    result=plan_edit("make this 2cm wider",selected,STATE,use_model=False)
    assert result["command"]["target_mm"]==25.
    blocked=plan_edit("put a 5mm hole here",selected,STATE,use_model=False)
    assert blocked["command"] is None
    assert "region" in blocked["explanation"]


def test_nonfinite_or_reversed_bounds_and_dimensions_rejected():
    with pytest.raises(ValidationError):
        Bounds(min=[0,0,0],max=[1,float("nan"),1])
    with pytest.raises(ValidationError):
        Bounds(min=[1,0,0],max=[0,1,1])
    with pytest.raises(ValidationError):
        Cylinder(op="cut_cylinder",radius_mm=math.inf,height_mm=10,center=[0,0,0])
    with pytest.raises(ValidationError):
        Resize(op="resize",axis="x",target_mm=-1)


def test_typed_model_numeric_error_is_corrected_by_independent_guard(monkeypatch):
    from pydantic_ai.models.test import TestModel
    monkeypatch.delenv("CADFORGE_EDIT_MODEL",raising=False)
    model=TestModel(custom_output_args={"command":{"op":"resize","axis":"x","target_mm":22.},
                                       "explanation":"Incorrectly interpreted cm as mm.","clarification":None})
    result=plan_edit("make this 2cm wider",SELECTION,STATE,use_model=True,model=model)
    assert result["command"]["target_mm"]==40.
    assert result["planner"]=="pydantic_ai_with_numeric_guard"
    assert result["usage"]["model_requests"]==1


def test_failed_model_fallback_is_labeled_and_does_not_claim_ai_success():
    result=plan_edit("move this 3 cm right",SELECTION,STATE,use_model=True,model="unsupported-provider:not-a-model")
    assert result["planner"]=="offline_fallback"
    assert result["fallback_reason"]
    assert result["command"]["amount_mm"]==30.


@pytest.mark.parametrize("prompt,expected", [
    ("make this 1 cm wider without moving or resizing the holes", {"op":"resize_preserving_holes","axis":"x","target_mm":30.,"min_wall_mm":1.}),
    ("make this 2 cm wider but preserve mounting holes", {"op":"resize_preserving_holes","axis":"x","target_mm":40.,"min_wall_mm":1.}),
    ("increase depth by 1 cm and keep the holes fixed", {"op":"resize_preserving_holes","axis":"y","target_mm":20.,"min_wall_mm":1.}),
    ("make this 1 inch wide and keep holes unchanged", {"op":"resize_preserving_holes","axis":"x","target_mm":25.4,"min_wall_mm":1.}),
    ("make this 1 cm wider and don't move the holes, minimum wall 0.2 cm", {"op":"resize_preserving_holes","axis":"x","target_mm":30.,"min_wall_mm":2.}),
])
def test_explicit_hole_preserving_resize_keeps_units_and_constraint(prompt,expected):
    result=plan_edit(prompt,SELECTION,STATE,use_model=False)
    assert result['command']==expected
    assert 'backend must validate' in result['explanation']


@pytest.mark.parametrize("prompt", [
    "make this 1 cm wider and preserve lever geometry and holes",
    "make this 1 cm wider and preserve pivot holes",
    "make this 1 cm shorter and preserve holes",
    "make this 1 cm narrower and preserve holes",
    "make this 1 cm wider and preserve holes and interfaces",
    "make this 1 cm wider and preserve holes and move it 3 mm right",
])
def test_unsupported_protected_invariants_remain_clarifications(prompt):
    result=plan_edit(prompt,SELECTION,STATE,use_model=False)
    assert result['command'] is None
    assert result['clarification']


def test_hole_protection_requires_whole_part_and_accepts_z_axis_schema():
    selection=SELECTION|{'region':{'min':[0,0,0],'max':[5,5,5]}}
    result=plan_edit('make this 1cm wider and preserve holes',selection,STATE,use_model=False)
    assert result['command'] is None
    assert 'whole part' in result['clarification']
    assert ResizePreservingHoles(op='resize_preserving_holes',axis='z',target_mm=20).axis == 'z'


def test_model_cannot_downgrade_hole_preservation_to_generic_scaling():
    from pydantic_ai.models.test import TestModel
    model=TestModel(custom_output_args={'command':{'op':'resize','axis':'x','target_mm':30.},
                                       'explanation':'Unsafe generic scale.', 'clarification':None})
    result=plan_edit('make this 1cm wider without moving or resizing the holes',SELECTION,STATE,use_model=True,model=model)
    assert result['command']['op']=='resize_preserving_holes'
    assert result['planner']=='pydantic_ai_with_numeric_guard'


@pytest.mark.parametrize("prompt", ["make this 1 cm taller and preserve holes", "increase height by 1 cm and keep holes fixed"])
def test_protected_height_retains_units(prompt):
    result=plan_edit(prompt,SELECTION,STATE,use_model=False)
    assert result['command']==dict(op='resize_preserving_holes',axis='z',target_mm=20.,min_wall_mm=1.)
