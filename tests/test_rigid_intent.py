import pytest
from cadforge.edit_planner import plan_edit
from cadforge.edit_learning import recommend
S={'part_id':'p','region':{'min':[-1,-11,-11],'max':[11,11,11]}}
STATE={'parts':[{'id':'p','bounds':[[-10,-10,-10],[10,10,10]]}]}
@pytest.mark.parametrize('prompt',[
 'Move this rigidly 7 mm right',
 'Move every selected point equally 7 mm right',
 'Move this 7 mm right without deforming',
 'Translate this 7 mm right without tapering',
])
def test_explicit_rigid_intent_survives_planning(prompt):
    r=plan_edit(prompt,S,STATE,use_model=False)
    assert r['command']['translation_mode']=='rigid',r
    assert r['command']['amount_mm']==7

def test_model_cannot_drop_rigid_contract():
    from pydantic_ai.models.test import TestModel
    model=TestModel(custom_output_args={'command':{'op':'translate','axis':'x','amount_mm':7,'translation_mode':'allow_transition'},'explanation':'move this','clarification':None})
    r=plan_edit('Move this rigidly 7 mm right',S,STATE,use_model=True,model=model)
    assert r['command']['translation_mode']=='rigid'

def test_rigid_request_does_not_retrieve_incompatible_repair(tmp_path):
    store=tmp_path/'corrupt.json';store.write_text('broken store')
    hint=recommend({'op':'translate','axis':'x','amount_mm':7,'translation_mode':'rigid'},path=store)
    assert hint['strategy'] is None and hint['skill_id'] is None
    assert store.read_text()=='broken store'
