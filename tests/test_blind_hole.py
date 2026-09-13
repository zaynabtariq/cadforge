from pathlib import Path
import math
import numpy as np
import pytest
import trimesh
from cadforge.workspace import PythonWorkspace


def stock(tmp_path,mesh=None):
    source=tmp_path/'stock.stl';(trimesh.creation.box(extents=[40,30,10]) if mesh is None else mesh).export(source)
    workspace=PythonWorkspace(tmp_path/'workspace');state=workspace.import_file(source)
    return workspace,state,{'part_id':state['parts'][0]['id']}


@pytest.mark.parametrize('direction,entry_z,bottom', [(-1,5,1),(1,-5,-1)])
def test_top_bottom_actual_depth_volume_commit_undo(tmp_path,direction,entry_z,bottom):
    workspace,state,selection=stock(tmp_path)
    original=workspace.export_path(state['id']).read_bytes()
    command={'op':'drill_blind_hole','radius_mm':3,'depth_mm':4,'entry':[0,0,entry_z],'direction':direction}
    preview=workspace.preview(state['id'],command,selection)
    assert preview['accepted'],preview
    result=trimesh.load(preview['parts'][0]['stl_path'],force='mesh')
    original_mesh=trimesh.load(state['parts'][0]['stl_path'],force='mesh')
    expected=32*9*math.sin(2*math.pi/64)*4
    assert original_mesh.volume-result.volume==pytest.approx(expected,rel=5e-6)
    hole_vertices=result.vertices[np.linalg.norm(result.vertices[:,:2],axis=1)<3.00001]
    assert (hole_vertices[:,2].min() if direction==-1 else hole_vertices[:,2].max())==pytest.approx(bottom,abs=1e-6)
    assert workspace.export_path(state['id']).read_bytes()==original
    workspace.commit(state['id'],preview['preview_id']);workspace.undo(state['id'])
    assert workspace.export_path(state['id']).read_bytes()==original


@pytest.mark.parametrize('entry,depth,direction', [([0,0,0],4,-1),([0,0,5],10,-1),([19,0,5],4,-1),([0,0,-5],4,-1)])
def test_invalid_entry_through_depth_and_edge_breakout_rollback(tmp_path,entry,depth,direction):
    workspace,state,selection=stock(tmp_path);original=workspace.export_path(state['id']).read_bytes()
    preview=workspace.preview(state['id'],{'op':'drill_blind_hole','radius_mm':3,'depth_mm':depth,'entry':entry,'direction':direction},selection)
    assert not preview['accepted']
    assert workspace.export_path(state['id']).read_bytes()==original
    with pytest.raises(ValueError):workspace.commit(state['id'],preview['preview_id'])


def test_preexisting_void_in_drill_path_fails_full_engagement(tmp_path):
    base=trimesh.creation.box(extents=[40,30,10]);void=trimesh.creation.cylinder(radius=1,height=20,sections=64)
    mesh=trimesh.boolean.difference([base,void],engine='manifold');workspace,state,selection=stock(tmp_path,mesh)
    preview=workspace.preview(state['id'],{'op':'drill_blind_hole','radius_mm':3,'depth_mm':4,'entry':[0,0,5],'direction':-1},selection)
    assert not preview['accepted']
    assert any(c['name']=='blind_hole.full_stock_engagement' and not c['passed'] for c in preview['checks'])


def test_local_notch_breakout_rejected_even_inside_global_bounds(tmp_path):
    base=trimesh.creation.box(extents=[40,30,10]);notch=trimesh.creation.box(extents=[4,8,8]);notch.apply_translation([3,0,4])
    mesh=trimesh.boolean.difference([base,notch],engine='manifold');workspace,state,selection=stock(tmp_path,mesh)
    preview=workspace.preview(state['id'],{'op':'drill_blind_hole','radius_mm':3,'depth_mm':4,'entry':[0,0,5],'direction':-1},selection)
    assert not preview['accepted']
    assert any(c['name']=='blind_hole.full_stock_engagement' and not c['passed'] for c in preview['checks'])


def test_tiny_through_passage_rejected_by_floor_topology_not_aggregate_tolerance(tmp_path):
    base=trimesh.creation.box(extents=[20,20,10]);tiny=trimesh.creation.cylinder(radius=.003,height=12,sections=32)
    mesh=trimesh.boolean.difference([base,tiny],engine='manifold');workspace,state,selection=stock(tmp_path,mesh)
    preview=workspace.preview(state['id'],{'op':'drill_blind_hole','radius_mm':2,'depth_mm':3,'entry':[0,0,5],'direction':-1},selection)
    assert not preview['accepted']
    assert any(c['name']=='blind_hole.closed_disk_floor' and not c['passed'] for c in preview['checks'])
    assert any(c['name']=='blind_hole.inward_tool_covered_by_stock' and not c['passed'] for c in preview['checks'])


def test_tiny_enclosed_void_above_floor_rejected_by_stock_coverage(tmp_path):
    base=trimesh.creation.box(extents=[20,20,10]);tiny=trimesh.creation.box(extents=[.006,.006,.006]);tiny.apply_translation([0,0,4])
    mesh=trimesh.boolean.difference([base,tiny],engine='manifold')
    # Direct helper keeps an enclosed cavity as one stock mesh; workspace import
    # intentionally separates disconnected shell meshes and is not used here.
    from cadforge.blind_hole import drill_blind_hole,BlindHoleError
    with pytest.raises(BlindHoleError) as failure:
        drill_blind_hole(mesh,2,3,[0,0,5],-1)
    assert any(c['name']=='blind_hole.inward_tool_covered_by_stock' and not c['passed'] for c in failure.value.checks)
