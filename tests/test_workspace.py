import numpy as np
import pytest
import trimesh
from cadforge.workspace import PythonWorkspace


@pytest.fixture
def workspace(tmp_path):
    source=tmp_path/'source.stl';trimesh.creation.box(extents=[10,12,14]).export(source)
    service=PythonWorkspace(tmp_path/'workspace',region_learning_path=tmp_path/'region-learning.json')
    return service,service.import_file(source)


def test_preview_is_nonmutating_commit_versions_and_undo_restores(workspace):
    service,state=workspace;selection={'part_id':state['parts'][0]['id']}
    old=service.export_path(state['id']).read_bytes()
    preview=service.preview(state['id'],{'op':'translate','axis':'x','amount_mm':5},selection)
    assert preview['accepted']
    assert service.state(state['id'])['revision']==0
    assert service.export_path(state['id']).read_bytes()==old
    committed=service.commit(state['id'],preview['preview_id'])
    assert committed['revision']==1 and committed['version']!=state['version']
    assert committed['parts'][0]['bounds'][0][0]==pytest.approx(0)
    restored=service.undo(state['id'])
    assert restored['revision']==2
    assert restored['parts'][0]['bounds']==state['parts'][0]['bounds']
    assert service.export_path(state['id']).read_bytes()==old
    with pytest.raises(ValueError,match='stale'):
        service.commit(state['id'],preview['preview_id'])


def test_plan_for_old_revision_cannot_edit_new_geometry(workspace):
    service,state=workspace;selection={'part_id':state['parts'][0]['id']}
    other=service.preview(state['id'],{'op':'resize','axis':'x','target_mm':20},selection)
    current=service.commit(state['id'],other['preview_id'])
    exported=service.export_path(state['id']).read_bytes()
    # Another agent committed while a planner was reasoning about the old size.
    with pytest.raises(ValueError,match='changed while planning'):
        service.preview(state['id'],{'op':'resize','axis':'x','target_mm':11},selection,expected_revision=state['revision'])
    assert service.state(state['id'])==current
    assert service.export_path(state['id']).read_bytes()==exported


def test_resize_and_boolean_preserve_valid_mesh(workspace):
    service,state=workspace;selection={'part_id':state['parts'][0]['id']}
    resized=service.preview(state['id'],{'op':'resize','axis':'x','target_mm':20},selection)
    assert resized['accepted']
    assert resized['parts'][0]['bounds'][1][0]-resized['parts'][0]['bounds'][0][0]==pytest.approx(20)
    cut=service.preview(state['id'],{'op':'cut_cylinder','radius_mm':1,'height_mm':30,'center':[0,0,0]},selection)
    assert cut['accepted']
    assert cut['parts'][0]['volume_mm3']<state['parts'][0]['volume_mm3']
    assert cut['parts'][0]['watertight']


def test_failed_preview_cannot_commit_or_change_geometry(workspace):
    service,state=workspace
    result=service.preview(state['id'],{'op':'resize','axis':'x','target_mm':-5},{'part_id':state['parts'][0]['id']})
    assert not result['accepted']
    assert any(not check['passed'] for check in result['checks'])
    assert service.state(state['id'])==state
    with pytest.raises(ValueError,match='rejected'):service.commit(state['id'],result['preview_id'])


def test_add_part_without_selection_and_original_retained(workspace):
    service,state=workspace
    result=service.preview(state['id'],{'op':'add_box','size':[2,3,4],'center':[20,0,0]}, {})
    assert result['accepted'] and len(result['parts'])==2
    assert result['parts'][0]['bounds']==state['parts'][0]['bounds']
    assert service.state(state['id'])['parts']==state['parts']


def test_units_and_component_import(tmp_path):
    original=trimesh.creation.box(extents=[1,1,1]);other=original.copy();other.apply_translation([3,0,0])
    source=tmp_path/'multi.stl';trimesh.util.concatenate([original,other]).export(source)
    service=PythonWorkspace(tmp_path/'ws');state=service.import_file(source,units='cm')
    assert len(state['parts'])==2
    assert state['parts'][0]['bounds'][1][0]-state['parts'][0]['bounds'][0][0]==pytest.approx(10)
    assert state['units']=='mm' and state['source_units']=='cm'


def test_safe_ids_and_unsupported_inputs(workspace,tmp_path):
    service,state=workspace
    with pytest.raises(ValueError):service.state('../escape')
    bad=tmp_path/'input.py';bad.write_text('raise RuntimeError')
    with pytest.raises(ValueError):service.import_file(bad)
    result=service.preview(state['id'],{'op':'exec','code':'anything'}, {})
    assert not result['accepted']


def test_step_retains_original_and_imports_solids(tmp_path):
    import cadquery as cq
    source=tmp_path/'bodies.step'
    first=cq.Workplane('XY').box(5,6,7).val()
    second=cq.Workplane('XY').box(2,2,2).translate((20,0,0)).val()
    cq.exporters.export(cq.Compound.makeCompound([first,second]),str(source))
    service=PythonWorkspace(tmp_path/'ws');state=service.import_file(source)
    assert len(state['parts'])==2
    assert all(p['watertight'] for p in state['parts'])
    from pathlib import Path
    assert Path(state['original_path']).read_bytes()==source.read_bytes()


def test_edit_one_part_preserves_other_export_bytes(tmp_path):
    first=trimesh.creation.box();second=first.copy();second.apply_translation([5,0,0])
    source=tmp_path/'parts.stl';trimesh.util.concatenate([first,second]).export(source)
    service=PythonWorkspace(tmp_path/'ws');state=service.import_file(source)
    selected,untouched=state['parts']
    from pathlib import Path
    original=Path(untouched['stl_path']).read_bytes()
    result=service.preview(state['id'],{'op':'translate','axis':'z','amount_mm':2},{'part_id':selected['id']})
    assert result['accepted']
    retained=next(p for p in result['parts'] if p['id']==untouched['id'])
    assert Path(retained['stl_path']).read_bytes()==original


def test_region_preview_preserves_unselected_vertices_without_commit(workspace):
    service,state=workspace
    selection={'part_id':state['parts'][0]['id'],'region':{'min':[0,-7,-8],'max':[6,7,8]}}
    preview=service.preview(state['id'],{'op':'translate','axis':'x','amount_mm':2},selection)
    assert preview['accepted'],preview['error']
    assert any('outside' in c['name'] and c['passed'] for c in preview['checks'])
    assert service.state(state['id'])['revision']==0
    assert preview['parts'][0]['bounds'][0][0]==state['parts'][0]['bounds'][0][0]
    assert preview['parts'][0]['bounds'][1][0]==pytest.approx(7)


def test_region_failure_records_trials_and_rolls_back(workspace):
    service,state=workspace
    selection={'part_id':state['parts'][0]['id'],'region':{'min':[0,-7,-8],'max':[6,7,8]}}
    preview=service.preview(state['id'],{'op':'translate','axis':'x','amount_mm':-20},selection)
    assert not preview['accepted']
    assert preview['repair_trials']
    assert service.state(state['id'])==state
