import json
import trimesh
from cadforge.workspace import PythonWorkspace
from cadforge import edit_learning, revalidate_learning


def stale_case(tmp_path, monkeypatch):
    source=tmp_path/'sphere.stl'
    trimesh.creation.icosphere(subdivisions=2,radius=10).export(source)
    service=PythonWorkspace(tmp_path/'workspace',region_learning_path=tmp_path/'learning.json')
    state=service.import_file(source);part=state['parts'][0]
    selection={'part_id':part['id'],'region':{'min':[-1,-11,-11],'max':[11,11,11]}}
    with monkeypatch.context() as patch:
        patch.setattr(edit_learning,'validator_context',lambda:'previous-validator')
        result=service.preview(state['id'],{'op':'translate','axis':'y','amount_mm':7},selection)
    assert result['accepted']
    return service,state,result


def test_replays_actual_failure_then_repair_once_per_context(tmp_path,monkeypatch):
    service,state,result=stale_case(tmp_path,monkeypatch)
    before=json.loads(service.region_learning_path.read_text())
    report=revalidate_learning.revalidate(service,tmp_path/'reports')
    assert report['published'] and report['cad_candidates']==2
    assert [t['accepted'] for t in report['replays'][0]['trials']]==[False,True]
    after=json.loads(service.region_learning_path.read_text())
    assert after['evidence'][0]==before['evidence'][0]
    assert len(after['evidence'])==2 and len(after['revalidations'])==1
    again=revalidate_learning.revalidate(service,tmp_path/'reports')
    assert again['published'] and again['cad_candidates']==0 and not again['replays']
    assert json.loads(service.region_learning_path.read_text())==after
    assert service.state(state['id'])==state


def test_missing_retained_case_blocks_publication_before_execution(tmp_path,monkeypatch):
    service,state,result=stale_case(tmp_path,monkeypatch)
    before=service.region_learning_path.read_bytes()
    (service._folder(state['id'])/'previews'/result['preview_id']/'preview.json').unlink()
    report=revalidate_learning.revalidate(service,tmp_path/'reports')
    assert not report['published'] and report['cad_candidates']==0
    assert service.region_learning_path.read_bytes()==before


def test_concurrent_store_update_is_preserved(tmp_path,monkeypatch):
    service,_,_=stale_case(tmp_path,monkeypatch)
    original=revalidate_learning.record_executed
    def concurrent(*args,**kwargs):
        receipt=original(*args,**kwargs)
        with edit_learning._store(service.region_learning_path) as stored:
            stored['concurrent_marker']='new-user-evidence'
            edit_learning._save(service.region_learning_path,stored)
        return receipt
    monkeypatch.setattr(revalidate_learning,'record_executed',concurrent)
    report=revalidate_learning.revalidate(service,tmp_path/'reports')
    assert not report['published'] and 'changed during replay' in report['error']
    stored=json.loads(service.region_learning_path.read_text())
    assert stored['concurrent_marker']=='new-user-evidence' and len(stored['evidence'])==1


def test_failed_retained_case_is_replayed_and_kept(tmp_path,monkeypatch):
    service,state,result=stale_case(tmp_path,monkeypatch)
    with monkeypatch.context() as patch:
        patch.setattr(edit_learning,'validator_context',lambda:'previous-validator')
        failure=service.preview(state['id'],{'op':'translate','axis':'y','amount_mm':100,'translation_mode':'rigid'},result['selection'])
    assert not failure['accepted']
    report=revalidate_learning.revalidate(service,tmp_path/'reports')
    assert report['published'] and len(report['replays'])==2
    assert report['replays'][1]['accepted'] is False
    assert report['replays'][1]['trials']
    stored=json.loads(service.region_learning_path.read_text())
    assert len(stored['evidence'])==4 and stored['evidence'][-1]['accepted'] is False


def test_forged_preview_identity_blocks_revalidation(tmp_path,monkeypatch):
    service,state,result=stale_case(tmp_path,monkeypatch)
    path=service._folder(state['id'])/'previews'/result['preview_id']/'preview.json'
    record=json.loads(path.read_text());record['session_id']='0'*32;path.write_text(json.dumps(record))
    before=service.region_learning_path.read_bytes()
    report=revalidate_learning.revalidate(service,tmp_path/'reports')
    assert not report['published'] and 'identity mismatch' in report['error']
    assert service.region_learning_path.read_bytes()==before


def test_new_validator_replays_original_cases_without_multiplying_lineage(tmp_path,monkeypatch):
    service,_,_=stale_case(tmp_path,monkeypatch)
    first=revalidate_learning.revalidate(service,tmp_path/'reports')
    assert first['published']
    monkeypatch.setattr(edit_learning,'validator_context',lambda:'next-validator')
    monkeypatch.setattr(revalidate_learning,'validator_context',lambda:'next-validator')
    second=revalidate_learning.revalidate(service,tmp_path/'reports')
    assert second['published'] and len(second['replays'])==1
    assert second['replays'][0]['old_evidence_id']==first['replays'][0]['old_evidence_id']
    stored=json.loads(service.region_learning_path.read_text())
    assert len(stored['evidence'])==3 and len(stored['revalidations'])==2
