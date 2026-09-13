import json
from pathlib import Path
import pytest
from cadforge.benchmark import Budget, make_cases, public_brief, freeze, verify, evaluate_hidden, evaluate_cases


def test_public_brief_does_not_leak_expected_contract():
    case = make_cases(1, 2)[0]
    assert set(public_brief(case)) == {'id','family','request'}
    assert 'expected' not in public_brief(case)


def test_dev_and_hidden_have_disjoint_parameter_tuples():
    dev = make_cases(6,41729)
    hidden = make_cases(20,1983,True,20)
    assert len(dev)==24 and len(hidden)==100
    signatures = {json.dumps(c['expected'], sort_keys=True) for c in dev}
    assert all(json.dumps(c['expected'],sort_keys=True) not in signatures for c in hidden if c['family'] != 'composite')


def test_commitment_detects_fixture_and_dev_tampering(tmp_path):
    private,public = tmp_path/'private',tmp_path/'public'
    first = freeze(private,public)
    assert freeze(private,public) == first
    (public/'development.json').write_text('[]')
    with pytest.raises(RuntimeError,match='integrity'):
        verify(private,public)


def test_hidden_single_use_and_no_detailed_feedback(tmp_path):
    private,public = tmp_path/'private',tmp_path/'public'
    freeze(private,public)
    def broken_runner(brief,mode,budget):
        assert set(brief)=={'id','family','request'}
        raise RuntimeError('candidate failed')
    result = evaluate_hidden(broken_runner, modes=['none'], private_dir=private,public_dir=public)
    assert result['results'][0]['passed']==0
    assert result['results'][0]['total']==100
    assert 'cases' not in result['results'][0]
    with pytest.raises(FileExistsError):
        evaluate_hidden(broken_runner,modes=['none'],private_dir=private,public_dir=public)


def test_budget_cannot_change_after_freeze(tmp_path):
    private,public = tmp_path/'private',tmp_path/'public'
    freeze(private,public)
    with pytest.raises(ValueError,match='Budget'):
        evaluate_hidden(lambda *_: {},budget=Budget(attempts=100),private_dir=private,public_dir=public)


def test_composite_fails_closed_and_no_partial_credit():
    case = make_cases(0,5,True,1)[0]
    result=evaluate_cases([case],lambda *_:{'usage':{'attempts':1,'tool_calls':1,'model_tokens':0}},'none',Budget(),True)
    assert result['passed']==0
    assert not result['engineering_ready']


def test_exported_box_cannot_masquerade_as_requested_bracket(tmp_path):
    import cadquery as cq
    from cadforge.benchmark import check_candidate
    from cadforge.geometry import build_design, export_design
    from cadforge.schema import DesignSpec
    case = next(c for c in make_cases(1,3) if c['family']=='bracket')
    spec = DesignSpec(family='bracket',parameters=case['expected'])
    exports = export_design(build_design(spec), tmp_path)
    cq.exporters.export(cq.Workplane('XY').box(10,10,10),exports['step'])
    checks = check_candidate(case,{'spec':spec,'exports':exports})
    assert not all(checks.values())
    assert not checks['design_envelope']


def test_missing_budget_counters_fails_even_if_geometry_passes(monkeypatch):
    import cadforge.benchmark as benchmark
    monkeypatch.setattr(benchmark,'check_candidate',lambda *_:{'valid_geometry':True})
    result=benchmark.evaluate_cases(make_cases(1,1)[:1],lambda *_:{},'none',Budget(),True)
    assert result['passed']==0
    assert not result['cases'][0]['checks']['budget']
