"""Real process deadline and report-boundary tests, not benchmark cases."""
import json
import os
from pathlib import Path
import sys
import time
import pytest
from cadforge.evaluation_process import run_worker


def run(code,tmp_path,timeout=2,limit=1000):
    return run_worker([sys.executable,'-c',code],{'request':'fixture'},timeout_seconds=timeout,
                      cwd=tmp_path,env={'PATH':os.environ['PATH']},maximum_output_bytes=limit)


def test_worker_receives_only_explicit_environment_and_json(tmp_path,monkeypatch):
    monkeypatch.setenv('CADFORGE_TEST_PRIVATE','must-not-inherit')
    result=run("import json,os,sys; p=json.load(sys.stdin); print(json.dumps({'received':p,'inherited':'CADFORGE_TEST_PRIVATE' in os.environ}))",tmp_path)
    assert result.status=='completed' and result.report=={'received':{'request':'fixture'},'inherited':False}


def test_timeout_stops_descendant_before_it_can_publish(tmp_path):
    child="import pathlib,time; time.sleep(.8); pathlib.Path('escaped').write_text('bad')"
    code=f"import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',{child!r}]); time.sleep(5)"
    result=run(code,tmp_path,timeout=.2)
    assert result.status=='timeout' and result.report is None
    assert result.elapsed_seconds<1
    time.sleep(.8)
    assert not (tmp_path/'escaped').exists()


def test_completed_worker_cannot_leave_background_work_running(tmp_path):
    child="import pathlib,time; time.sleep(.8); pathlib.Path('escaped').write_text('bad')"
    code=f"import subprocess,sys; subprocess.Popen([sys.executable,'-c',{child!r}]); print('{{\"done\": true}}')"
    result=run(code,tmp_path)
    assert result.status=='completed'
    time.sleep(.8)
    assert not (tmp_path/'escaped').exists()


@pytest.mark.parametrize('code,status',[
    ("print('not json')",'invalid_report'),
    ("print('[]')",'invalid_report'),
    ("raise SystemExit(2)",'worker_failed'),
    ("print('x'*2000)",'output_limit'),
    ("print('{\"count\": NaN}')",'invalid_report'),
    ("print('{\"passed\": false, \"passed\": true}')",'invalid_report'),
])
def test_invalid_reports_cannot_count_as_completed(code,status,tmp_path):
    assert run(code,tmp_path).status==status
