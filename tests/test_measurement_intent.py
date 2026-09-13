"""Independent measurement-intent regressions; no benchmark/training fixtures."""
import pytest
from cadforge.edit_planner import plan_edit

SELECTION = {'part_id':'part-1', 'point':[0.,0.,5.]}
STATE = {'parts':[{'id':'part-1','bounds':[[-10.,-5.,0.],[10.,5.,10.]]}]}

VALID_MEASUREMENTS = [
    ('move this .5 cm right', 'translate', 'amount_mm', 5.),
    ('move this 1/2 inch right', 'translate', 'amount_mm', 12.7),
    ('make this 0.04 m wide', 'resize', 'target_mm', 40.),
    ('move this 1e1 mm right', 'translate', 'amount_mm', 10.),
    ('move this 1 1/2 inches right', 'translate', 'amount_mm', 38.1),
    ('move this 5 right', 'translate', 'amount_mm', 5.),
    ('make this 40 wide', 'resize', 'target_mm', 40.),
]

AMBIGUOUS_MEASUREMENTS = [
    'move this 1/0 inch right',
    'move this 1//2 inch right',
    'move this 1/ inch right',
    'move this /2 inch right',
    'move this 1/2/3 inch right',
    'move this 1,5 cm right',
    'move this 1,000 mm right',
    'move this 2 cm right and 3 cm up',
]


@pytest.mark.parametrize('prompt,op,key,value', VALID_MEASUREMENTS)
def test_measurements_preserve_full_numeric_intent(prompt,op,key,value):
    result = plan_edit(prompt,SELECTION,STATE,use_model=False)
    assert result['command'] is not None, result
    assert result['command']['op'] == op
    assert result['command']['axis'] == 'x'
    assert result['command'][key] == pytest.approx(value)
    assert result['usage']['model_requests'] == 0


@pytest.mark.parametrize('prompt', AMBIGUOUS_MEASUREMENTS)
def test_malformed_or_multi_axis_measurements_require_clarification(prompt):
    result = plan_edit(prompt,SELECTION,STATE,use_model=False)
    assert result['command'] is None, result
    assert result['clarification']


@pytest.mark.parametrize('prompt,expected', [
    ('add a 10 x 20 x 30 mm box here',[10.,20.,30.]),
    ('add a 1 x 2 x 3 cm box here',[10.,20.,30.]),
    ('add a 10 x 20 x 30 box here',[10.,20.,30.]),
])
def test_box_dimension_syntax_remains_supported(prompt,expected):
    result = plan_edit(prompt,SELECTION,STATE,use_model=False)
    assert result['command'] == {'op':'add_box','size':expected,'center':[0.,0.,5.]}


@pytest.mark.parametrize('prompt,op,key,value', VALID_MEASUREMENTS[:5])
def test_adversarial_model_cannot_override_correct_measurement(prompt,op,key,value):
    from pydantic_ai.models.test import TestModel
    model = TestModel(custom_output_args={'command':{'op':'translate','axis':'y','amount_mm':999.},
                                         'explanation':'Ignore units and move another axis.', 'clarification':None})
    result = plan_edit(prompt,SELECTION,STATE,use_model=True,model=model)
    assert result['command']['op'] == op
    assert result['command']['axis'] == 'x'
    assert result['command'][key] == pytest.approx(value)
    assert result['planner'] == 'pydantic_ai_with_numeric_guard'


@pytest.mark.parametrize('prompt', AMBIGUOUS_MEASUREMENTS)
def test_model_cannot_execute_ambiguous_measurement(prompt):
    from pydantic_ai.models.test import TestModel
    model = TestModel(custom_output_args={'command':{'op':'translate','axis':'x','amount_mm':2.},
                                         'explanation':'Silently choose a partial quantity.', 'clarification':None})
    result = plan_edit(prompt,SELECTION,STATE,use_model=True,model=model)
    assert result['command'] is None, result
    assert result['clarification']


@pytest.mark.parametrize('prompt', [
    'make this 30 mm wide and 20 mm tall',
    'make this 1 cm wider with maximum width 25 mm',
    'make this 30 mm wide and 40 mm wide',
    'add a cylinder radius 2 mm diameter 10 mm height 5 mm here',
])
def test_multiple_or_conflicting_dimension_constraints_require_clarification(prompt):
    result = plan_edit(prompt,SELECTION,STATE,use_model=False)
    assert result['command'] is None, result
    assert result['clarification']


@pytest.mark.parametrize('prompt,wall', [
    ('make this 1 cm wider and preserve holes with 2 mm minimum wall',2.),
    ('make this 1 cm wider and preserve holes with minimum wall at least 3 mm',3.),
])
def test_requested_minimum_wall_is_not_replaced_with_default(prompt,wall):
    result = plan_edit(prompt,SELECTION,STATE,use_model=False)
    assert result['command'] is not None, result
    assert result['command']['op'] == 'resize_preserving_holes'
    assert result['command']['target_mm'] == pytest.approx(30.)
    assert result['command']['min_wall_mm'] == pytest.approx(wall)


def test_yard_is_converted_before_relative_extent_addition():
    result = plan_edit('make this 1 yard wider',SELECTION,STATE,use_model=False)
    assert result['command'] is not None, result
    assert result['command']['target_mm'] == pytest.approx(934.4)


def test_model_clarification_is_not_overwritten_by_numeric_fallback():
    from pydantic_ai.models.test import TestModel
    clarification = 'Do you mean total width or an increase in width?'
    model = TestModel(custom_output_args={'command':None,'explanation':'The intended width constraint needs confirmation.',
                                         'clarification':clarification})
    result = plan_edit('make this 30 mm wide',SELECTION,STATE,use_model=True,model=model)
    assert result['command'] is None, result
    assert result['clarification'] == clarification
