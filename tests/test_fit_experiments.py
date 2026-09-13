import hashlib
import json
from pathlib import Path
import pytest

import cadforge.fit_experiments as experiments


PARAMETERS={'fastener_diameter':2.,'radial_clearance':.1,'min_wall':1.,
            'bore_diameter':2.,'boss_outer_diameter':10.,'family_code':0.}


def read_log(measurement):
    assert len(measurement.artifact_digests)==1
    path,digest=next(iter(measurement.artifact_digests.items()))
    path=Path(path)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
    return path,json.loads(path.read_text())


def test_partial_trials_survive_execution_exception_with_matching_hash(monkeypatch,tmp_path):
    actual=experiments.measure_coupon
    calls=0
    def injected(parameters):
        nonlocal calls
        calls+=1
        if calls==2:
            raise RuntimeError('injected kernel failure after first measured trial')
        return actual(parameters)
    monkeypatch.setattr(experiments,'measure_coupon',injected)
    measured=experiments.boundary_executor('bore_diameter',tmp_path)(PARAMETERS,'fault-case')
    assert not measured.passed
    assert measured.failure_codes==('execution:RuntimeError',)
    path,log=read_log(measured)
    assert len(log['trials'])==2
    assert log['trials'][0]['measurements']['screw_overlap_mm3']>0
    assert log['trials'][0]['checks']['screw_insertion_clearance'] is False
    assert log['trials'][1]['execution_exception']['type']=='RuntimeError'
    assert log['execution_exception']['trial_index']==1
    assert measured.measurements['cad_trials']==2


def test_boundary_logs_success_and_does_not_allow_case_path_traversal(tmp_path):
    logs=tmp_path/'logs'
    execute=experiments.boundary_executor('bore_diameter',logs)
    result=execute(PARAMETERS,'../../escaped')
    path,log=read_log(result)
    assert path.parent==logs.resolve()
    assert log['case_id']=='../../escaped'
    assert not (tmp_path.parent/'escaped.json').exists()
    assert log['execution_exception'] is None
    assert log['trials'][-1]['passed']
    assert result.measurements['bore_diameter']==pytest.approx(2.2)
    # Initial failure remains discovery evidence; successful boundary is measured.
    assert not result.passed
    repeated=execute(PARAMETERS,'../../escaped')
    assert next(iter(repeated.artifact_digests))!=str(path)
    assert path.exists()


def test_verification_exception_is_retained_and_hashed(monkeypatch,tmp_path):
    def fail(_):
        raise ValueError('invalid shape fixture')
    monkeypatch.setattr(experiments,'measure_coupon',fail)
    result=experiments.verification_executor(tmp_path)(PARAMETERS,'/tmp/must-not-write')
    path,log=read_log(result)
    assert path.parent==tmp_path.resolve()
    assert not result.passed
    assert log['execution_exception']['type']=='ValueError'
