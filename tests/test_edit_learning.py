import json
import trimesh

from cadforge.workspace import PythonWorkspace
from cadforge import region_edit
from cadforge.edit_learning import recommend


def import_mesh(service,path,mesh):
    mesh.export(path)
    return service.import_file(path)


def preview(service,state,amount):
    lo,hi=state['parts'][0]['bounds']
    region={'min':[-1,lo[1]-1,lo[2]-1],'max':[hi[0]+1,hi[1]+1,hi[2]+1]}
    return service.preview(state['id'],{'op':'translate','axis':'y','amount_mm':amount},
                           {'part_id':state['parts'][0]['id'],'region':region})


def test_actual_correction_transfer_and_single_attempt_reuse(tmp_path,monkeypatch):
    service=PythonWorkspace(tmp_path/'ws',region_learning_path=tmp_path/'learning.json')
    actual=region_edit.deform_region
    invocations=0
    def counted(*args,**kwargs):
        nonlocal invocations
        invocations+=1
        return actual(*args,**kwargs)
    monkeypatch.setattr(region_edit,'deform_region',counted)
    sphere=import_mesh(service,tmp_path/'sphere.stl',trimesh.creation.icosphere(subdivisions=2,radius=10))
    first=preview(service,sphere,7)
    assert first['accepted'],first['error']
    assert first['learning']['status']=='candidate'
    assert first['learning']['attempts']==2
    capsule=import_mesh(service,tmp_path/'capsule.stl',trimesh.creation.capsule(height=12,radius=8,count=[12,12]))
    second=preview(service,capsule,5)
    assert second['accepted'],second['error']
    assert second['learning']['status']=='promoted'
    third_mesh=trimesh.creation.capsule(height=15,radius=9,count=[12,12])
    third_state=import_mesh(service,tmp_path/'third.stl',third_mesh)
    third=preview(service,third_state,5)
    assert third['accepted'],third['error']
    assert third['learning']['status']=='reused'
    assert third['learning']['attempts']==1
    assert third['learning']['transition_semantics']
    assert 'not a rigid translation' in third['learning']['semantics']
    assert invocations==3, 'Learning must not execute geometry a second time'
    stored=json.loads((tmp_path/'learning.json').read_text())
    assert len(stored['evidence'])==3 and len(stored['skills'])==1
    # Same strategy must not leak into an unrelated resize operation.
    assert recommend({'op':'resize','axis':'y'},path=tmp_path/'learning.json')['strategy'] is None


def test_small_same_topology_variants_do_not_claim_transfer(tmp_path):
    service=PythonWorkspace(tmp_path/'ws',region_learning_path=tmp_path/'learning.json')
    for i,radius in enumerate((10,10.1)):
        state=import_mesh(service,tmp_path/f'sphere-{i}.stl',trimesh.creation.icosphere(subdivisions=2,radius=radius))
        result=preview(service,state,7)
        assert result['accepted']
        assert result['learning']['status']=='candidate'
    stored=json.loads((tmp_path/'learning.json').read_text())
    assert not stored['skills']


def test_failed_preview_is_persisted_and_validator_context_blocks_stale_policy(tmp_path,monkeypatch):
    from cadforge import edit_learning
    service=PythonWorkspace(tmp_path/'ws',region_learning_path=tmp_path/'learning.json')
    state=import_mesh(service,tmp_path/'box.stl',trimesh.creation.box(extents=[10,12,14]))
    result=service.preview(state['id'],{'op':'translate','axis':'x','amount_mm':-20},
        {'part_id':state['parts'][0]['id'],'region':{'min':[0,-7,-8],'max':[6,7,8]}})
    assert not result['accepted']
    assert result['learning']['status']=='failed_recorded'
    stored=json.loads((tmp_path/'learning.json').read_text())
    assert stored['evidence'][0]['trials']
    assert not stored['evidence'][0]['accepted']
    stored['skills'].append({'id':'old','context':'old-context','axis':'y','strategy':'interior_transition_power_1'})
    (tmp_path/'learning.json').write_text(json.dumps(stored))
    monkeypatch.setattr(edit_learning,'validator_context',lambda:'new-context')
    assert recommend({'op':'translate','axis':'y'},path=tmp_path/'learning.json')['strategy'] is None


def test_promoted_transition_remains_usable_after_rigid_rejection(tmp_path):
    service=PythonWorkspace(tmp_path/'ws',region_learning_path=tmp_path/'learning.json')
    sphere=import_mesh(service,tmp_path/'sphere.stl',trimesh.creation.icosphere(subdivisions=2,radius=10))
    assert preview(service,sphere,7)['learning']['status']=='candidate'
    capsule=import_mesh(service,tmp_path/'capsule.stl',trimesh.creation.capsule(height=12,radius=8,count=[12,12]))
    assert preview(service,capsule,5)['learning']['status']=='promoted'
    command={'op':'translate','axis':'y','amount_mm':7}
    before=recommend(command,path=tmp_path/'learning.json')
    assert before['strategy']
    lo,hi=sphere['parts'][0]['bounds']
    result=service.preview(sphere['id'],command|{'translation_mode':'rigid'},
        {'part_id':sphere['parts'][0]['id'],'region':{'min':[-1,lo[1]-1,lo[2]-1],'max':[hi[0]+1,hi[1]+1,hi[2]+1]}})
    assert not result['accepted']
    assert result['learning']['status']=='failed_recorded'
    assert result['learning_hint']['skill_id'] is None
    assert recommend(command,path=tmp_path/'learning.json')==before
    later=preview(service,sphere,7)
    assert later['learning']['status']=='reused'
    assert later['learning']['attempts']==1
    saved=json.loads((tmp_path/'learning.json').read_text())
    assert not saved['quarantines'], 'Incompatible rigid requests must not quarantine a valid transition strategy'


def test_easy_success_cannot_resurrect_strategy_after_real_counterexample(tmp_path):
    service=PythonWorkspace(tmp_path/'ws',region_learning_path=tmp_path/'learning.json')
    sphere=import_mesh(service,tmp_path/'sphere.stl',trimesh.creation.icosphere(subdivisions=2,radius=10))
    capsule=import_mesh(service,tmp_path/'capsule.stl',trimesh.creation.capsule(height=12,radius=8,count=[12,12]))
    assert preview(service,sphere,7)['learning']['status']=='candidate'
    assert preview(service,capsule,5)['learning']['status']=='promoted'
    failed=preview(service,sphere,100)
    assert not failed['accepted']
    assert failed['learning']['status']=='quarantined'
    repaired=preview(service,sphere,7)
    assert repaired['accepted']
    assert repaired['learning']['status']=='quarantined_family'
    store=tmp_path/'learning.json'
    saved=json.loads(store.read_text())
    assert len(saved['skills'])==1
    assert len(saved['evidence'])==4
    # Also reject old stores containing an alias promoted before this fix.
    saved['skills'].append(saved['skills'][0]|{'id':'historical-alias'})
    store.write_text(json.dumps(saved))
    assert recommend({'op':'translate','axis':'y'},path=store)['strategy'] is None
    from cadforge.edit_learning import history
    report=history(path=store)
    assert len(report['skills'])==2
    assert all(s['current_status']=='quarantined' and not s['eligible_for_reuse'] for s in report['skills'])


def test_counterexample_before_first_promotion_is_not_forgotten(tmp_path):
    service=PythonWorkspace(tmp_path/'ws',region_learning_path=tmp_path/'learning.json')
    sphere=import_mesh(service,tmp_path/'sphere.stl',trimesh.creation.icosphere(subdivisions=2,radius=10))
    capsule=import_mesh(service,tmp_path/'capsule.stl',trimesh.creation.capsule(height=12,radius=8,count=[12,12]))
    assert preview(service,sphere,7)['learning']['status']=='candidate'
    assert not preview(service,sphere,100)['accepted']
    result=preview(service,capsule,5)
    assert result['accepted']
    assert result['learning']['status']=='quarantined_family'
    saved=json.loads((tmp_path/'learning.json').read_text())
    assert not saved['skills']
    assert recommend({'op':'translate','axis':'y'},path=tmp_path/'learning.json')['strategy'] is None
