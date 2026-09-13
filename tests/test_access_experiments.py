import pytest
from cadforge.access_experiments import measure_access


@pytest.mark.parametrize('family',[0,1,2])
def test_clearance_failure_and_repair_preserve_lower_stock(family):
    parameters={'tool_diameter':6.,'radial_clearance':.2,'pocket_diameter':6.,'family_code':family}
    failed=measure_access(parameters)
    assert not failed.passed and failed.failure_codes==('tool_corridor',)
    repaired=measure_access(parameters|{'pocket_diameter':6.4})
    assert repaired.passed and repaired.checks['lower_stock_unchanged']
    assert repaired.measurements['removed_lower_mm3']<1e-7


def test_partial_discovery_cost_and_failure_survive_kernel_exception(tmp_path,monkeypatch):
    import json,hashlib
    from cadforge import access_experiments as access
    original=access.measure_access;calls=[]
    def interrupted(parameters):
        calls.append(dict(parameters))
        if len(calls)==2:raise RuntimeError('injected kernel interruption')
        return original(parameters)
    monkeypatch.setattr(access,'measure_access',interrupted)
    parameters={'tool_diameter':6.,'radial_clearance':.2,'pocket_diameter':6.}
    result=access.access_executor(tmp_path,discover=True)(parameters,'../../untrusted-case')
    assert not result.passed and result.measurements['cad_trials']==2
    assert result.failure_codes==('execution:RuntimeError',)
    from pathlib import Path
    path,digest=next(iter(result.artifact_digests.items()));path=Path(path)
    assert path.parent==tmp_path
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
    audit=json.loads(path.read_text())
    assert len(audit['trials'])==2 and audit['attempted_cad_trials']==2
    assert audit['trials'][0]['failure_codes']==['tool_corridor']
    assert audit['trials'][1]['execution_exception']['trial_index']==1
    assert calls[1]['pocket_diameter']==6.1


def test_nonfinite_measurement_is_failure_not_training_evidence(tmp_path,monkeypatch):
    from cadforge import access_experiments as access
    from cadforge.continual import Measurement
    monkeypatch.setattr(access,'measure_access',lambda p:Measurement(True,{'pocket_diameter':float('nan')},(),{'valid_solid':True}))
    result=access.access_executor(tmp_path)({'pocket_diameter':6.4},'nonfinite')
    assert not result.passed and result.measurements['cad_trials']==1
    assert result.failure_codes==('execution:ValueError',)
    assert result.artifact_digests
