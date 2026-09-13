import json
from types import SimpleNamespace
import cadquery as cq
from cadforge.schema import DesignSpec
from cadforge.handoff import write_handoff,verify_handoff


def test_named_exports_roundtrip_and_changed_file_is_detected(tmp_path):
    source=tmp_path/'design.py';source.write_text('raise RuntimeError("must never execute")')
    shape=cq.Workplane('XY').box(12,20,3).val()
    result=SimpleNamespace(spec=DesignSpec(family='glasses'),parts={'test_plate':shape})
    manifest=write_handoff(result,{'python':str(source)},tmp_path)
    data=json.loads(open(manifest).read())
    assert verify_handoff(manifest)['integrity_passed']
    part=data['parts'][0]
    restored=cq.importers.importStep(str(tmp_path/part['exports']['step'])).val()
    assert abs(restored.Volume()-720)<1e-7
    assert part['solid_count']==1 and abs(part['volume_mm3']-720)<1e-7
    assert data['units']=='mm' and data['production_ready'] is False
    source.write_text('changed')
    assert verify_handoff(manifest)['failures']==[{'path':'design.py','reason':'file identity changed'}]
    (tmp_path/part['exports']['stl']).unlink()
    assert len(verify_handoff(manifest)['failures'])==2


def valid_inventory(tmp_path):
    import hashlib
    names=['design.py','parts/plate.step','parts/plate.stl']
    for name in names:
        path=tmp_path/name;path.parent.mkdir(exist_ok=True);path.write_bytes(b'inert test bytes')
    identity={'bytes':16,'sha256':hashlib.sha256(b'inert test bytes').hexdigest()}
    return {'version':1,'units':'mm','production_ready':False,'specification':{'family':'glasses'},
            'files':{name:dict(identity) for name in names},
            'parts':[{'name':'plate','exports':{'step':names[1],'stl':names[2]},'solid_count':1,
                      'volume_mm3':1,'bounds_mm':[[0,0,0],[1,1,1]]}]}


def test_empty_and_malformed_manifests_never_pass(tmp_path):
    path=tmp_path/'manufacturing-manifest.json'
    for text in ['{"files":{}}','{}','[]','null','{','{"files":{},"files":{}}']:
        path.write_text(text)
        assert not verify_handoff(path)['integrity_passed']


def test_incomplete_or_invalid_inventory_never_passes(tmp_path):
    import copy
    data=valid_inventory(tmp_path);path=tmp_path/'manufacturing-manifest.json'
    path.write_text(json.dumps(data));assert verify_handoff(path)['integrity_passed']
    cases=[]
    for field,value in [('parts',[]),('units','cm'),('version',True),('production_ready',True)]:
        changed=copy.deepcopy(data);changed[field]=value;cases.append(changed)
    changed=copy.deepcopy(data);del changed['files']['design.py'];cases.append(changed)
    changed=copy.deepcopy(data);del changed['files']['parts/plate.step'];cases.append(changed)
    changed=copy.deepcopy(data);changed['parts'].append(copy.deepcopy(changed['parts'][0]));cases.append(changed)
    changed=copy.deepcopy(data);changed['parts'][0]['bounds_mm'][0][0]=float('nan');cases.append(changed)
    changed=copy.deepcopy(data);changed['files']['design.py']['bytes']=True;cases.append(changed)
    changed=copy.deepcopy(data);changed['files']['../outside.py']=changed['files'].pop('design.py');cases.append(changed)
    for changed in cases:
        path.write_text(json.dumps(changed));assert not verify_handoff(path)['integrity_passed']


def test_symlink_escape_is_not_read_as_package_content(tmp_path):
    data=valid_inventory(tmp_path);path=tmp_path/'manufacturing-manifest.json'
    outside=tmp_path.parent/(tmp_path.name+'-outside.py');outside.write_bytes(b'inert test bytes')
    (tmp_path/'design.py').unlink();(tmp_path/'design.py').symlink_to(outside)
    path.write_text(json.dumps(data))
    result=verify_handoff(path)
    assert not result['integrity_passed']
    assert result['failures']==[{'path':'design.py','reason':'path escapes package'}]


def test_review_evidence_is_complete_and_changes_are_detected(tmp_path):
    from cadforge.handoff import inventory_review_evidence
    manifest=tmp_path/'manufacturing-manifest.json';manifest.write_text(json.dumps(valid_inventory(tmp_path)))
    evidence={role:tmp_path/(role+'.json') for role in ['prebuild_contract','prebuild_layout','engineering','geometry_screen']}
    for file in evidence.values():file.write_text('{"production_ready":false}')
    inventory_review_evidence(manifest,evidence)
    assert verify_handoff(manifest)['integrity_passed']
    evidence['engineering'].write_text('{"production_ready":true}')
    result=verify_handoff(manifest)
    assert not result['integrity_passed']
    assert result['failures']==[{'path':'engineering.json','reason':'file identity changed'}]


def test_missing_review_role_does_not_publish_partial_manifest(tmp_path):
    import pytest
    from cadforge.handoff import inventory_review_evidence
    manifest=tmp_path/'manufacturing-manifest.json';manifest.write_text(json.dumps(valid_inventory(tmp_path)))
    before=manifest.read_bytes();report=tmp_path/'engineering.json';report.write_text('{}')
    with pytest.raises(ValueError,match='Incomplete review evidence'):
        inventory_review_evidence(manifest,{'engineering':report})
    assert manifest.read_bytes()==before


def test_packaged_recipe_is_inventoried_and_source_changes_fail(tmp_path):
    source=tmp_path/'design.py';source.write_text('# inert source')
    result=SimpleNamespace(spec=DesignSpec(family='glasses'),parts={'plate':cq.Workplane('XY').box(2,3,4).val()})
    manifest=write_handoff(result,{'python':source},tmp_path)
    data=json.loads(open(manifest).read())
    assert 'regeneration/src/cadforge/production_geometry.py' in data['regeneration_files']
    assert 'regeneration/requirements.txt' in data['regeneration_files']
    assert all(name in data['files'] for name in data['regeneration_files'])
    recipe=tmp_path/'regeneration/src/cadforge/production_geometry.py'
    recipe.write_text('# replaced source')
    report=verify_handoff(manifest)
    assert not report['integrity_passed']
    assert report['failures']==[{'path':'regeneration/src/cadforge/production_geometry.py','reason':'file identity changed'}]


def test_recipe_snapshot_covers_relative_imports_inside_functions():
    import ast
    from pathlib import Path
    from cadforge import regeneration
    for filename in regeneration.RECIPE_MODULES:
        tree=ast.parse(Path(regeneration.__file__).with_name(filename).read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom) and node.level:
                assert node.level==1 and node.module
                assert node.module.split('.')[0]+'.py' in regeneration.RECIPE_MODULES
