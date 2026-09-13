import json
from cadforge.schema import DesignSpec
from cadforge.pipeline import run_design, discover

def test_repair_preserves_explicit_bad_constraint(tmp_path):
    result=run_design(DesignSpec(family='bracket',parameters={'wall':.4}),tmp_path)
    assert not result['passed']
    assert result['history'][-1]['parameters']['wall']==.4

def test_discovery_regression_and_transfer(tmp_path):
    report=discover(tmp_path)
    assert report['promoted_skills']==3
    assert report['transfer']['none']['cost']['attempts']>report['transfer']['learned']['cost']['attempts']
    assert report['transfer']['retrieved']['passed']
    assert report['discovery_cost']['attempts']>0
    # Exact same command succeeds after restart; no hidden ingestion API.
    from cadforge.skills import SkillLibrary
    lib=SkillLibrary.load(tmp_path/'skills.json')
    assert lib.compose(report['composed_skill_id'],{'wall':.1,'clearance':.05})['wall']>=1.2

def test_zero_budget_does_not_execute(tmp_path):
    result=run_design(DesignSpec(family='bracket'),tmp_path,max_attempts=0)
    assert result['cost']['attempts']==0
    assert not result['passed']

def test_typed_planner_test_model(monkeypatch):
    from pydantic_ai.models.test import TestModel
    from cadforge.planner import plan_with_model
    model=TestModel(custom_output_args={'family':'bracket','parameters':{'width':40},'name':'test'})
    spec,usage=plan_with_model('bracket',model=model)
    assert spec.family=='bracket'
    assert usage['requests']==1
