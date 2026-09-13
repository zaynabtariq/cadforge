import pytest
from pydantic_ai import Agent,ModelRetry
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.messages import ModelResponse,TextPart
from cadforge.execution_budget import ExecutionBudget,BudgetExceeded
from cadforge.model_budget import budgeted_model


def test_validation_retry_is_denied_before_second_provider_request():
    calls=[]
    def provider(messages,info):
        calls.append(1);return ModelResponse(parts=[TextPart('retry')])
    budget=ExecutionBudget({'model_requests':1})
    with budget.activate():
        agent=Agent(budgeted_model(FunctionModel(provider)),retries=2)
        @agent.output_validator
        def reject(output):raise ModelRetry('Try again')
        with pytest.raises(BudgetExceeded):agent.run_sync('test')
    assert len(calls)==1
    assert budget.snapshot()=={'limits':{'model_requests':1},'used':{'model_requests':1},'denied':{'model_requests':1}}


def test_separate_agent_runs_share_request_limit():
    calls=[]
    def provider(messages,info):
        calls.append(1);return ModelResponse(parts=[TextPart('ok')])
    budget=ExecutionBudget({'model_requests':1})
    with budget.activate():
        assert Agent(budgeted_model(FunctionModel(provider))).run_sync('first').output=='ok'
        with pytest.raises(BudgetExceeded):Agent(budgeted_model(FunctionModel(provider))).run_sync('second')
    assert len(calls)==1


def test_threaded_specialists_inherit_one_atomic_budget():
    from types import SimpleNamespace
    from cadforge.scheduler import run_specialists
    from cadforge.execution_budget import charge
    jobs=[SimpleNamespace(id=str(i),discipline='test',lens='budget') for i in range(8)]
    def worker(job):charge('model_requests');return {'executed':True}
    budget=ExecutionBudget({'model_requests':3})
    with budget.activate():rows=run_specialists(jobs,worker,max_workers=4)
    assert sum(r['status']=='completed' for r in rows)==3
    assert budget.snapshot()['used']['model_requests']==3
    assert budget.snapshot()['denied']['model_requests']==5


def test_stream_request_is_denied_before_provider_starts():
    import asyncio
    calls=[]
    async def stream(messages,info):
        calls.append(1)
        yield 'ok'
    async def run():
        budget=ExecutionBudget({'model_requests':0})
        with budget.activate():
            agent=Agent(budgeted_model(FunctionModel(stream_function=stream)))
            with pytest.raises(BudgetExceeded):
                async with agent.run_stream('test') as result:await result.get_output()
        assert not calls and budget.snapshot()['denied']['model_requests']==1
    asyncio.run(run())


def test_edit_planner_does_not_hide_budget_exhaustion_with_offline_fallback():
    from cadforge.edit_planner import plan_edit
    def provider(messages,info):raise AssertionError('Provider must not execute')
    budget=ExecutionBudget({'model_requests':0})
    with budget.activate():
        with pytest.raises(BudgetExceeded):
            plan_edit('move this 3 cm right',{'part_id':'p'},
                {'parts':[{'id':'p','bounds':[[-10,-5,0],[10,5,10]]}]},
                use_model=True,model=FunctionModel(provider))
    assert budget.snapshot()['denied']['model_requests']==1
