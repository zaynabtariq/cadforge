"""Independent portability and hostile-input audit for versioned project archives."""
import base64
import copy
import json
from pathlib import Path
import numpy as np
import pytest
import trimesh
from cadforge.workspace import PythonWorkspace


@pytest.fixture
def archived_project(tmp_path):
    source = tmp_path / 'original.stl'
    trimesh.creation.box(extents=[10,12,14]).export(source)
    workspace = PythonWorkspace(tmp_path / 'source-workspace')
    initial = workspace.import_file(source)
    selection = {'part_id':initial['parts'][0]['id']}
    exports = [workspace.export_path(initial['id']).read_bytes()]
    commands = [{'op':'translate','axis':'x','amount_mm':3.}, {'op':'resize','axis':'y','target_mm':18.}]
    states = [initial]
    for command in commands:
        preview = workspace.preview(initial['id'],command,selection)
        assert preview['accepted']
        states.append(workspace.commit(initial['id'],preview['preview_id']))
        exports.append(workspace.export_path(initial['id']).read_bytes())
    return workspace,states,exports,commands,source


def test_fresh_workspace_restore_retains_original_commands_and_ancestor_undo(archived_project,tmp_path):
    workspace,states,exports,commands,source = archived_project
    archive = workspace.export_project(states[-1]['id'])
    target = PythonWorkspace(tmp_path / 'empty-target')
    restored = target.import_project(archive)
    assert restored['id'] != states[-1]['id']
    assert target.export_path(restored['id']).read_bytes() == exports[-1]
    assert Path(restored['original_path']).read_bytes() == source.read_bytes()
    retained_commands = [entry['command'] for entry in restored['history'] if entry['action']=='commit']
    assert retained_commands == commands
    for expected in reversed(exports[:-1]):
        target.undo(restored['id'])
        assert target.export_path(restored['id']).read_bytes() == expected
    with pytest.raises(ValueError):target.undo(restored['id'])
    for path in target.root.rglob('state.json'):
        state = json.loads(path.read_text())
        for part in state['parts']:
            assert Path(part['stl_path']).is_relative_to(target.root)
            assert Path(part['stl_path']).is_file()
        assert Path(state['original_path']).is_relative_to(target.root)


def test_export_after_undo_preserves_live_revision_history_not_stale_snapshot(archived_project,tmp_path):
    workspace,states,exports,commands,source = archived_project
    current = workspace.undo(states[-1]['id'])
    assert current['revision'] > states[-2]['revision']
    archive = workspace.export_project(current['id'])
    target = PythonWorkspace(tmp_path / 'fresh-undo-target')
    restored = target.import_project(archive)
    assert restored['revision'] == current['revision']
    assert [x['action'] for x in restored['history']] == [x['action'] for x in current['history']]
    assert restored['history'][-1]['action'] == 'undo'
    assert target.export_path(restored['id']).read_bytes() == exports[1]
    target.undo(restored['id'])
    assert target.export_path(restored['id']).read_bytes() == exports[0]


def corrupt_payload(payload,attack):
    value = copy.deepcopy(payload)
    if attack == 'blob_hash':
        key = next(iter(value['blobs']))
        value['blobs'][key] = base64.b64encode(b'corrupted geometry').decode()
    elif attack == 'path_extension':value['original']['extension'] = '/../../outside.stl'
    elif attack == 'version_path':
        key = next(iter(value['versions']))
        value['versions']['../../outside'] = value['versions'].pop(key)
    elif attack == 'nan':value['current']['revision'] = float('nan')
    elif attack == 'unknown_parent':value['current']['parent_version'] = 'f'*32
    elif attack == 'cycle':
        key = value['current']['version']
        value['current']['parent_version'] = key
        value['versions'][key]['parent_version'] = key
    elif attack == 'blob_wrong_type':value['current']['parts'][0]['blob'] = []
    elif attack == 'original_blob_wrong_type':value['original']['blob'] = {}
    elif attack == 'embedded_part_path':value['current']['parts'][0]['stl_path'] = '/tmp/untrusted.stl'
    elif attack == 'embedded_original_path':value['current']['original_path'] = '/tmp/untrusted.step'
    elif attack == 'missing_blob':
        value['current']['parts'][0]['blob'] = '0'*64
    else:raise AssertionError(attack)
    return value


@pytest.mark.parametrize('attack',['blob_hash','path_extension','version_path','nan','unknown_parent','cycle','missing_blob','blob_wrong_type','original_blob_wrong_type','embedded_part_path','embedded_original_path'])
def test_hostile_archives_reject_before_publishing_any_session(archived_project,tmp_path,attack):
    workspace,states,*_ = archived_project
    archive = workspace.export_project(states[-1]['id'])
    payload = json.loads(Path(archive).read_text())
    bad = tmp_path / (attack+'.cadforge')
    bad.write_text(json.dumps(corrupt_payload(payload,attack)))
    target = PythonWorkspace(tmp_path / 'empty-target')
    before = set(target.root.iterdir())
    with pytest.raises(ValueError):target.import_project(bad)
    assert set(target.root.iterdir()) == before, 'Rejected import published a partial project or leaked staging files'
    assert not list(target.root.rglob('session.json'))
    assert not (tmp_path / 'outside.stl').exists()


def test_recommitted_branch_restores_its_actual_ancestor_chain(archived_project,tmp_path):
    workspace,states,exports,commands,source = archived_project
    current = workspace.undo(states[-1]['id'])
    branch_command = {'op':'translate','axis':'z','amount_mm':2.}
    preview = workspace.preview(current['id'],branch_command,{'part_id':current['parts'][0]['id']})
    assert preview['accepted']
    current = workspace.commit(current['id'],preview['preview_id'])
    branch_bytes = workspace.export_path(current['id']).read_bytes()
    target = PythonWorkspace(tmp_path / 'branch-target')
    restored = target.import_project(workspace.export_project(current['id']))
    assert target.export_path(restored['id']).read_bytes() == branch_bytes
    assert [x['command'] for x in restored['history'] if x['action']=='commit'] == commands+[branch_command]
    target.undo(restored['id'])
    assert target.export_path(restored['id']).read_bytes() == exports[1]
    target.undo(restored['id'])
    assert target.export_path(restored['id']).read_bytes() == exports[0]


def test_original_step_bytes_survive_portable_mesh_project(tmp_path):
    import cadquery as cq
    source = tmp_path / 'parametric_source.step'
    cq.exporters.export(cq.Workplane('XY').box(10,12,14),str(source))
    workspace = PythonWorkspace(tmp_path / 'step-source')
    current = workspace.import_file(source)
    target = PythonWorkspace(tmp_path / 'step-target')
    restored = target.import_project(workspace.export_project(current['id']))
    assert Path(restored['original_path']).suffix == '.step'
    assert Path(restored['original_path']).read_bytes() == source.read_bytes()
    assert target.export_path(restored['id']).read_bytes() == workspace.export_path(current['id']).read_bytes()
    assert restored['history_trust'] == 'imported-unverified'
