"""Independent recovery of retained real trials; retries must not rerun CAD."""
import json
from pathlib import Path
import pytest
import trimesh
from cadforge import edit_learning, region_edit
from cadforge.workspace import PythonWorkspace


def evidence(path):
    return json.loads(path.read_text())['evidence'] if path.exists() else []


@pytest.fixture
def failed_audit(tmp_path,monkeypatch,request):
    store = tmp_path / 'learning.json'
    service = PythonWorkspace(tmp_path / 'workspace',region_learning_path=store)
    source = tmp_path / 'sphere.stl'
    trimesh.creation.icosphere(subdivisions=2,radius=10).export(source)
    state = service.import_file(source)
    lo,hi = state['parts'][0]['bounds']
    selection = {'part_id':state['parts'][0]['id'],
                 'region':{'min':[-1,lo[1]-1,lo[2]-1],'max':[hi[0]+1,hi[1]+1,hi[2]+1]}}
    recorder = edit_learning.record_executed
    ambiguous = getattr(request,'param','before') == 'after'
    def unavailable(*args,**kwargs):
        if ambiguous:recorder(*args,**kwargs)
        raise OSError('Simulated learning-store write outage')
    monkeypatch.setattr(edit_learning,'record_executed',unavailable)
    preview = service.preview(state['id'],{'op':'translate','axis':'y','amount_mm':7.},selection)
    assert preview['accepted'], preview
    assert preview['learning']['status'] == 'audit_failed'
    assert len(evidence(store)) == (1 if ambiguous else 0)
    monkeypatch.setattr(edit_learning,'record_executed',recorder)
    def forbidden(*args,**kwargs):raise AssertionError('Recovery reran CAD instead of using retained trials')
    monkeypatch.setattr(region_edit,'deform_region',forbidden)
    return service,state,preview,store


def test_retry_persists_real_failed_then_repaired_trials_once_without_cad_rerun(failed_audit):
    service,state,preview,store = failed_audit
    original = service.export_path(state['id']).read_bytes()
    first_receipt = service.retry_learning(state['id'],preview['preview_id'])
    saved = evidence(store)
    assert len(saved) == 1
    assert saved[0]['preview_id'] == preview['preview_id']
    assert saved[0]['actual_correction'] and saved[0]['measured_success']
    assert len(saved[0]['trials']) == 2
    assert saved[0]['trials'][0]['strategy'] == 'sharp'
    assert not saved[0]['trials'][0]['accepted']
    assert saved[0]['trials'][1]['accepted']
    before = store.read_bytes()
    second_receipt = service.retry_learning(state['id'],preview['preview_id'])
    assert second_receipt['evidence_id'] == first_receipt['evidence_id']
    assert second_receipt['status'] == first_receipt['status']
    assert second_receipt['attempts'] == first_receipt['attempts']
    assert second_receipt['deduplicated']
    assert store.read_bytes() == before
    assert len(evidence(store)) == 1
    assert service.export_path(state['id']).read_bytes() == original
    assert service.state(state['id'])['revision'] == state['revision']


def test_changed_source_mesh_prevents_recording_stale_trials(failed_audit):
    service,state,preview,store = failed_audit
    source = Path(state['parts'][0]['stl_path'])
    source.write_bytes(source.read_bytes()+b'changed source bytes')
    with pytest.raises(ValueError):service.retry_learning(state['id'],preview['preview_id'])
    assert not evidence(store)


def test_changed_validator_context_prevents_recording_stale_trials(failed_audit,monkeypatch):
    service,state,preview,store = failed_audit
    monkeypatch.setattr(edit_learning,'validator_context',lambda:'changed-validator-context')
    with pytest.raises(ValueError):service.retry_learning(state['id'],preview['preview_id'])
    assert not evidence(store)


def test_imported_archive_cannot_promote_without_local_preview_receipt(failed_audit,tmp_path):
    service,state,preview,store = failed_audit
    archive = service.export_project(state['id'])
    other_store = tmp_path / 'imported-learning.json'
    target = PythonWorkspace(tmp_path / 'imported-workspace',region_learning_path=other_store)
    restored = target.import_project(archive)
    with pytest.raises(ValueError):target.retry_learning(restored['id'],preview['preview_id'])
    assert not evidence(other_store)


@pytest.mark.parametrize('failed_audit',['after'],indirect=True)
def test_ambiguous_store_write_recovers_existing_evidence_without_duplicate_promotion(failed_audit):
    service,state,preview,store = failed_audit
    before = store.read_bytes()
    stored = evidence(store)
    assert len(stored) == 1
    receipt = service.retry_learning(state['id'],preview['preview_id'])
    assert receipt['deduplicated']
    assert receipt['evidence_id'] == stored[0]['id']
    assert store.read_bytes() == before
    assert len(evidence(store)) == 1
    assert not json.loads(store.read_text())['skills'], 'One topology cannot establish transfer'


def test_history_endpoint_uses_workspace_store(failed_audit,monkeypatch):
    from fastapi.testclient import TestClient
    from cadforge import studio_server
    service,state,preview,store=failed_audit
    receipt=service.retry_learning(state['id'],preview['preview_id'])
    monkeypatch.setattr(studio_server,'workspace',service)
    response=TestClient(studio_server.app).get('/api/learning')
    assert response.status_code==200
    assert [row['id'] for row in response.json()['evidence']]==[receipt['evidence_id']]
