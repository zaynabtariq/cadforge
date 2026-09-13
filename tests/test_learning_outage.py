import json
import trimesh
from cadforge.workspace import PythonWorkspace
from cadforge import region_edit,edit_learning


def run_preview(tmp_path,monkeypatch):
    source=tmp_path/'sphere.stl';trimesh.creation.icosphere(subdivisions=2,radius=10).export(source)
    service=PythonWorkspace(tmp_path/'ws',region_learning_path=tmp_path/'learning.json')
    state=service.import_file(source);original=service.export_path(state['id']).read_bytes()
    actual=region_edit.deform_region;calls=[]
    def counted(*args,**kwargs):
        calls.append(1);return actual(*args,**kwargs)
    monkeypatch.setattr(region_edit,'deform_region',counted)
    result=service.preview(state['id'],{'op':'translate','axis':'y','amount_mm':7},
        {'part_id':state['parts'][0]['id'],'region':{'min':[-1,-11,-11],'max':[11,11,11]}})
    assert result['accepted'],result
    assert calls==[1], 'Learning outage must not repeat geometry execution'
    assert service.export_path(state['id']).read_bytes()==original
    assert result['learning']['status']=='audit_failed'
    assert len(result['repair_trials'])==2
    assert not result['repair_trials'][0]['accepted'] and result['repair_trials'][1]['accepted']
    persisted=json.loads((service.root/state['id']/'previews'/result['preview_id']/'preview.json').read_text())
    assert persisted['repair_trials']==result['repair_trials']
    assert persisted['learning_hint']['strategy'] is None
    return result


def test_corrupt_learning_store_preserved_and_trials_survive(tmp_path,monkeypatch):
    path=tmp_path/'learning.json';path.write_text('{broken')
    result=run_preview(tmp_path,monkeypatch)
    assert path.read_text()=='{broken'
    assert 'JSONDecodeError' in result['learning_retrieval_error']


def test_unavailable_store_does_not_turn_checked_edit_into_failure(tmp_path,monkeypatch):
    def unavailable(*args,**kwargs):raise PermissionError('store unavailable')
    monkeypatch.setattr(edit_learning,'recommend',unavailable)
    monkeypatch.setattr(edit_learning,'record_executed',unavailable)
    result=run_preview(tmp_path,monkeypatch)
    assert 'PermissionError' in result['learning_retrieval_error']
    assert not (tmp_path/'learning.json').exists()
