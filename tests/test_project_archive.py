import hashlib
import json
from pathlib import Path
import pytest
import trimesh
from cadforge.workspace import PythonWorkspace


def fixture(tmp_path):
    source=tmp_path/'stock.stl';trimesh.creation.box(extents=[20,20,10]).export(source)
    workspace=PythonWorkspace(tmp_path/'source');state=workspace.import_file(source)
    preview=workspace.preview(state['id'],{'op':'drill_blind_hole','radius_mm':2,'depth_mm':3,'entry':[0,0,5],'direction':-1},{'part_id':state['parts'][0]['id']})
    assert preview['accepted']
    state=workspace.commit(state['id'],preview['preview_id'])
    return workspace,state


def test_original_bytes_and_feature_provenance_roundtrip(tmp_path):
    source,state=fixture(tmp_path);archive=source.export_project(state['id'])
    target=PythonWorkspace(tmp_path/'target');restored=target.import_project(archive)
    assert Path(restored['original_path']).read_bytes()==Path(state['original_path']).read_bytes()
    assert restored['history'][-1]['created_features']==state['history'][-1]['created_features']
    assert restored['history_trust']=='imported-unverified'
    assert restored['id']!=state['id'] and restored['parts'][0]['id']!=state['parts'][0]['id']
    assert all(Path(part['stl_path']).is_relative_to(target.root) for part in restored['parts'])
    original=target.undo(restored['id'])
    assert original['parts'][0]['volume_mm3']==pytest.approx(4000)
    # Re-export/import an imported project keeps its edits portable.
    third=PythonWorkspace(tmp_path/'third');again=third.import_project(target.export_project(restored['id']))
    assert again['history_trust']=='imported-unverified'


def test_export_rejects_symlink_source_escape(tmp_path):
    workspace,state=fixture(tmp_path)
    part=Path(state['parts'][0]['stl_path']);outside=tmp_path/'outside.stl';outside.write_bytes(part.read_bytes());part.unlink();part.symlink_to(outside)
    with pytest.raises(ValueError,match='outside workspace'):workspace.export_project(state['id'])


@pytest.mark.parametrize('damage',['overflow','duplicate_key','blob_bytes','unused_blob','nonwatertight'])
def test_corruption_never_publishes_session(tmp_path,damage):
    source,state=fixture(tmp_path);archive=source.export_project(state['id']);data=json.loads(archive.read_text())
    if damage=='overflow':payload=archive.read_text().replace('"revision":1','"revision":1e999',1)
    elif damage=='duplicate_key':payload=archive.read_text().replace('"format":','"format":"other","format":',1)
    else:
        if damage=='blob_bytes':data['blobs'][next(iter(data['blobs']))]='AAAA'
        elif damage=='unused_blob':
            import base64
            data['blobs'][hashlib.sha256(b'junk').hexdigest()]=base64.b64encode(b'junk').decode()
        else:
            import base64
            broken=trimesh.creation.box();broken.update_faces(list(range(11)));raw=broken.export(file_type='stl');digest=hashlib.sha256(raw).hexdigest()
            old=data['current']['parts'][0]['blob'];data['blobs'][digest]=base64.b64encode(raw).decode();del data['blobs'][old]
            data['current']['parts'][0]['blob']=digest;data['versions'][data['current']['version']]['parts'][0]['blob']=digest
        payload=json.dumps(data)
    invalid=tmp_path/'bad.cadforge';invalid.write_text(payload);target=PythonWorkspace(tmp_path/'target')
    with pytest.raises((ValueError,TypeError)):target.import_project(invalid)
    assert list(target.root.iterdir())==[]


def test_version_limit_preflight(tmp_path,monkeypatch):
    from cadforge import project_archive
    source,state=fixture(tmp_path);archive=source.export_project(state['id'])
    monkeypatch.setattr(project_archive,'MAX_VERSIONS',1)
    target=PythonWorkspace(tmp_path/'target')
    with pytest.raises(ValueError,match='version'):target.import_project(archive)
    assert not list(target.root.iterdir())
