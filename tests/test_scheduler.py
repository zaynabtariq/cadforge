from threading import Lock
import time
import pytest

from cadforge.agents import build_specialist_jobs, deterministic_worker
from cadforge.scheduler import BudgetExceeded, BudgetLedger, run_specialists


def test_108_unique_jobs_bounded_concurrency_and_error_audit():
    jobs = build_specialist_jobs("glasses with camera and Raspberry Pi")
    assert len(jobs) == len({j.id for j in jobs}) == 108
    lock, current, maximum = Lock(), 0, 0
    def worker(job):
        nonlocal current, maximum
        with lock:
            current += 1
            maximum = max(maximum, current)
        time.sleep(.002)
        with lock:
            current -= 1
        if job.id == jobs[4].id:
            raise RuntimeError("deliberate worker failure")
        return deterministic_worker(job)
    result = run_specialists(jobs, worker, max_workers=4)
    assert 1 < maximum <= 4
    assert len(result) == 108
    assert sum(r["status"] == "failed" for r in result) == 1
    assert result[0]["output"]["execution_kind"] == "deterministic_checklist"
    assert result[4]["job_id"] == jobs[4].id


def test_budget_atomic_failure_and_equal_arm_caps():
    arms = [BudgetLedger(max_attempts=3, max_tool_calls=5, max_model_tokens=100) for _ in range(3)]
    for arm in arms:
        arm.consume(attempts=1, tool_calls=2, model_tokens=90)
        previous = arm.snapshot()
        with pytest.raises(BudgetExceeded):
            arm.consume(attempts=1, tool_calls=1, model_tokens=11)
        assert arm.snapshot() == previous
        with pytest.raises(ValueError):
            arm.consume(tool_calls=-1)
    assert arms[0].snapshot() == arms[1].snapshot() == arms[2].snapshot()


def test_duplicate_specialist_ids_rejected():
    job = build_specialist_jobs("bracket")[0]
    with pytest.raises(ValueError, match="unique"):
        run_specialists([job, job], deterministic_worker)


def test_typed_llm_worker_in_thread_pool_with_test_provider(monkeypatch):
    pytest.importorskip("pydantic_ai")
    from pydantic_ai.models.test import TestModel
    from cadforge.agents import make_llm_worker
    monkeypatch.delenv("CADFORGE_MODEL", raising=False)
    model = TestModel(custom_output_args={"recommendation": "Increase camera clearance.",
                                         "relevant_parameters": ["camera_clearance"],
                                         "risks": ["Requires actual geometry validation."]})
    worker = make_llm_worker(model=model)
    results = run_specialists(build_specialist_jobs("camera glasses")[:4], worker, 2)
    assert all(r["status"] == "completed" for r in results), results
    assert all(r["output"]["model_requests"] > 0 for r in results)
