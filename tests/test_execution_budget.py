import pytest
import trimesh
from cadforge.execution_budget import ExecutionBudget,BudgetExceeded
from cadforge.workspace import PythonWorkspace


def imported(tmp_path,mesh):
    source=tmp_path/'stock.stl';mesh.export(source)
    service=PythonWorkspace(tmp_path/'ws',region_learning_path=tmp_path/'learning.json')
    return service,service.import_file(source)


def test_region_repair_cannot_spend_second_candidate_or_learn_unattempted_failure(tmp_path):
    service,state=imported(tmp_path,trimesh.creation.icosphere(subdivisions=2,radius=10))
    part=state['parts'][0];lo,hi=part['bounds']
    selection={'part_id':part['id'],'region':{'min':[-1,lo[1]-1,lo[2]-1],'max':[hi[0]+1,hi[1]+1,hi[2]+1]}}
    command={'op':'translate','axis':'y','amount_mm':7}
    budget=ExecutionBudget({'cad_candidates':1})
    with budget.activate():result=service.preview(state['id'],command,selection)
    assert not result['accepted'] and result['budget_exhausted']=='cad_candidates'
    assert len(result['repair_trials'])==1 and not result['repair_trials'][0]['accepted']
    assert result['learning']['status']=='budget_censored'
    assert not (tmp_path/'learning.json').exists()
    assert service.state(state['id'])==state
    budget=ExecutionBudget({'cad_candidates':2})
    with budget.activate():repaired=service.preview(state['id'],command,selection)
    assert repaired['accepted'] and len(repaired['repair_trials'])==2
    assert budget.snapshot()['used']['cad_candidates']==2


def test_sequence_shares_budget_and_rolls_back_when_second_step_denied(tmp_path):
    service,state=imported(tmp_path,trimesh.creation.box(extents=[10,10,10]))
    selection={'part_id':state['parts'][0]['id']}
    steps=[{'command':{'op':'translate','axis':axis,'amount_mm':1},'selection':selection} for axis in ('x','y')]
    budget=ExecutionBudget({'cad_candidates':1})
    with budget.activate():result=service.preview_sequence(state['id'],steps)
    assert not result['accepted'] and result['budget_exhausted']=='cad_candidates'
    assert result['step_outcomes'][0]['accepted'] and not result['step_outcomes'][1]['accepted']
    assert service.state(state['id'])==state
    assert budget.snapshot()['used']['cad_candidates']==1


def test_nested_work_cannot_replace_budget_and_denied_charges_do_not_execute():
    budget=ExecutionBudget({'tool_calls':1})
    with budget.activate():
        with pytest.raises(ValueError,match='inherit'):
            with ExecutionBudget({'tool_calls':100}).activate():pass
        budget.charge('tool_calls')
        with pytest.raises(BudgetExceeded):budget.charge('tool_calls')
    assert budget.snapshot()=={'limits':{'tool_calls':1},'used':{'tool_calls':1},'denied':{'tool_calls':1}}
