import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from cadforge.shared_budget import SharedExecutionBudget
from cadforge.execution_budget import BudgetExceeded,charge


def test_processes_share_one_limit_and_denials_survive_restart(tmp_path):
    path=tmp_path/'budget.sqlite3';budget=SharedExecutionBudget(path,{'cad_candidates':3})
    code='''import json,sys
from cadforge.shared_budget import SharedExecutionBudget
from cadforge.execution_budget import BudgetExceeded
b=SharedExecutionBudget(sys.argv[1])
try:
 b.charge('cad_candidates');print(json.dumps({'executed':True}))
except BudgetExceeded:print(json.dumps({'executed':False}))
'''
    env={'PATH':os.environ['PATH'],'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src')}
    workers=[subprocess.Popen([sys.executable,'-c',code,str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env) for _ in range(8)]
    results=[]
    for worker in workers:
        output,error=worker.communicate(timeout=20)
        assert worker.returncode==0,error
        results.append(json.loads(output))
    assert sum(r['executed'] for r in results)==3
    assert SharedExecutionBudget(path).snapshot()=={'limits':{'cad_candidates':3},'used':{'cad_candidates':3},'denied':{'cad_candidates':5}}
    with pytest.raises(FileExistsError):SharedExecutionBudget(path,{'cad_candidates':100})
    assert budget.snapshot()['used']['cad_candidates']==3


def test_shared_budget_uses_existing_context_hooks(tmp_path):
    budget=SharedExecutionBudget(tmp_path/'budget.sqlite3',{'model_requests':1})
    with budget.activate():
        charge('model_requests')
        with pytest.raises(BudgetExceeded):charge('model_requests')
    assert budget.snapshot()['denied']['model_requests']==1


def test_missing_or_invalid_attach_does_not_reset_budget(tmp_path):
    import sqlite3
    path=tmp_path/'missing.sqlite3'
    with pytest.raises(sqlite3.OperationalError):SharedExecutionBudget(path)
    assert not path.exists()
    with pytest.raises(ValueError):SharedExecutionBudget(path,{'cad_candidates':True})
    assert not path.exists()
