"""Persisted failed sequence evidence must outlive scratch transactions."""
import json
from pathlib import Path
import numpy as np
import pytest
import trimesh
from cadforge.workspace import PythonWorkspace,_identifier
from cadforge.edit_learning import recommend
from cadforge.revalidate_learning import _source,_fingerprint


@pytest.mark.parametrize('after_successful_step',[False,True])
def test_quarantined_sequence_input_and_preview_are_durable(tmp_path,after_successful_step):
    store=tmp_path/'learning.json';service=PythonWorkspace(tmp_path/'workspace',region_learning_path=store)
    cases=[]
    for name,mesh,amount in [('sphere',trimesh.creation.icosphere(subdivisions=2,radius=10),7),('capsule',trimesh.creation.capsule(height=12,radius=8,count=[12,12]),5)]:
        source=tmp_path/(name+'.stl');mesh.export(source);state=service.import_file(source);part=state['parts'][0];lo,hi=part['bounds']
        selection={'part_id':part['id'],'region':{'min':[-1,lo[1]-1,lo[2]-1],'max':[hi[0]+1,hi[1]+1,hi[2]+1]}}
        assert service.preview(state['id'],{'op':'translate','axis':'y','amount_mm':amount},selection)['accepted']
        cases.append((state,selection))
    assert recommend({'op':'translate','axis':'y'},path=store)['skill_id']
    state,selection=cases[0]
    failing={'command':{'op':'translate','axis':'y','amount_mm':100},'selection':selection}
    safe={'command':{'op':'translate','axis':'z','amount_mm':1},'selection':{'part_id':selection['part_id']}}
    steps=[safe,failing] if after_successful_step else [failing,safe]
    result=service.preview_sequence(state['id'],steps)
    assert not result['accepted'] and service.state(state['id'])==state
    evidence=json.loads(store.read_text())['evidence'][-1]
    outcome=result['step_outcomes'][-1]
    receipt=outcome['retained_counterexample']
    _identifier(evidence['preview_id'])
    assert evidence['preview_id']==receipt['preview_id']
    # Resolver must work after TemporaryDirectory cleanup and service restart.
    restarted=PythonWorkspace(service.root,region_learning_path=store)
    source=_source(restarted,evidence)
    assert source.is_file() and source.is_relative_to(service.root)
    loaded=trimesh.load(source,force='mesh',process=True)
    assert _fingerprint(loaded)==evidence['mesh_sha256']
    initial=trimesh.load(state['parts'][0]['stl_path'],force='mesh',process=True)
    assert np.allclose(loaded.bounds,initial.bounds+([0,0,1] if after_successful_step else [0,0,0]))
    retained=json.loads((service._folder(state['id'])/'previews'/receipt['preview_id']/'preview.json').read_text())
    assert retained['repair_trials']==evidence['trials']==outcome['repair_trials']
    assert retained['command']==evidence['command'] and retained['selection']['region']==evidence['region']
    assert retained['audit_only'] and not retained['accepted']
    assert retained['composition_lineage']['step_index']==(2 if after_successful_step else 1)
    with pytest.raises(ValueError):restarted.commit(state['id'],receipt['preview_id'])
    assert recommend({'op':'translate','axis':'y'},path=store)['skill_id'] is None
    assert len(json.loads(store.read_text())['skills'])==1
