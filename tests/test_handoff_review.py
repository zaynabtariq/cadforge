import json
from types import SimpleNamespace
import cadquery as cq
import pytest
from cadforge.schema import DesignSpec
from cadforge.handoff import write_handoff
from cadforge.handoff_review import review_handoff


def package(tmp_path):
    path=tmp_path/'package';path.mkdir()
    source=path/'design.py';source.write_text('raise RuntimeError("Do not execute")')
    spec=DesignSpec(family='glasses')
    result=SimpleNamespace(spec=spec,parts={'chassis':cq.Workplane('XY').box(10,10,10).val()})
    return write_handoff(result,{'python':source},path),spec


def test_wrong_package_spec_rejected_before_creating_review(tmp_path):
    path,spec=package(tmp_path)
    with pytest.raises(ValueError,match='specification differs'):
        review_handoff(path,DesignSpec(family='glasses',parameters={'lens_width':54}),tmp_path/'review')
    assert not (tmp_path/'review').exists()


def test_fresh_review_rejects_unrelated_valid_box_without_running_source(tmp_path):
    path,spec=package(tmp_path)
    result=review_handoff(path,spec,tmp_path/'review')
    assert not result['source_executed'] and not result['production_ready']
    assert not result.get('error')
    failed=[g['name'] for g in result['engineering']['gates'] if g['status']=='fail']
    assert 'geometry.required_parts' in failed
    assert (tmp_path/'review/review-contract.json').exists()
    assert json.loads((tmp_path/'review/review-result.json').read_text())==result


def test_mcp_review_routes_explicit_spec_to_independent_review(monkeypatch,tmp_path):
    import asyncio
    from cadforge import handoff_review,mcpserver
    seen=[]
    def reviewer(path,spec,out,*,review_inputs=None):
        seen.append((path,spec,review_inputs));return {'production_ready':False,'source_executed':False}
    monkeypatch.setattr(handoff_review,'review_handoff',reviewer)
    monkeypatch.setattr(mcpserver,'ARTIFACTS',tmp_path)
    result=asyncio.run(mcpserver.create_server().call_tool('review_camera_glasses_handoff',{
        'manifest_path':'explicit-package.json','expected_specification':{'family':'glasses','parameters':{'lens_width':54}}}))
    assert not result.is_error
    assert seen[0][1].parameters['lens_width']==54 and seen[0][2] is None


def test_rehashed_wrong_mesh_is_not_hidden_by_valid_step_review(tmp_path):
    import hashlib,trimesh
    from pathlib import Path
    path,spec=package(tmp_path);path=Path(path)
    mesh=path.parent/'parts/chassis.stl'
    trimesh.creation.box(extents=[10,10,20]).export(mesh)
    manifest=json.loads(path.read_text());body=mesh.read_bytes()
    manifest['files']['parts/chassis.stl']={'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()}
    path.write_text(json.dumps(manifest))
    result=review_handoff(path,spec,tmp_path/'review')
    assert result['package_unchanged'] and not result['export_consistent']
    assert result['geometry_screen']['integrity']['integrity_passed']
    assert not result['geometry_screen']['geometry_passed']
    assert result['engineering']['gates']


def test_changed_package_invalidates_review_receipt(tmp_path,monkeypatch):
    from pathlib import Path
    from cadforge import handoff_review
    path,spec=package(tmp_path);original=handoff_review.assess_geometry
    def changing(parts,contract):
        result=original(parts,contract)
        (Path(path).parent/'design.py').write_text('# concurrently changed')
        return result
    monkeypatch.setattr(handoff_review,'assess_geometry',changing)
    result=review_handoff(path,spec,tmp_path/'review')
    assert not result['package_unchanged'] and not result['export_consistent']
    assert 'changed during review' in result['error']
