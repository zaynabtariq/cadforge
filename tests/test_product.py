"""Product-boundary tests: external constraints, evidence timing and MCP parity."""
import asyncio
import hashlib
import json
from pathlib import Path

import cadquery as cq
import pytest
from cadforge.schema import DesignSpec
from cadforge.product import run_production


@pytest.fixture
def isolated_product(monkeypatch,tmp_path):
    import cadforge.evolve as evolution
    monkeypatch.setattr(evolution,'DEFAULT_DB',tmp_path/'unused-learning.sqlite3')
    return tmp_path/'product'


def test_prebuild_contract_exists_before_geometry_and_hash_matches(monkeypatch,isolated_product):
    import cadforge.production_geometry as geometry
    original=geometry.build_design
    observed=[]
    def inspect_build(spec):
        path=isolated_product/'prebuild-contract.json'
        assert path.is_file(), 'Required layout evidence must precede candidate generation'
        observed.append(path.read_bytes())
        return original(spec)
    monkeypatch.setattr(geometry,'build_design',inspect_build)
    result=run_production(DesignSpec(family='glasses',parameters={'lens_width':53,'temple_length':146,'board_height':7}),isolated_product)
    assert len(observed)==1
    assert result['prebuild_contract_sha256']==hashlib.sha256(observed[0]).hexdigest()
    assert result['parameters']['lens_width']==53
    assert result['parameters']['temple_length']==146
    assert result['parameters']['pi_component_height']==7
    assert result['requested_parameters']['board_height']==7
    assert result['production_ready'] is False
    persisted=json.loads((isolated_product/'engineering.json').read_text())
    assert persisted['engineering']['gates']
    assert all(g['status'] in ('pass','fail','blocked') for g in persisted['engineering']['gates'])


def test_deceptive_candidate_produces_machine_readable_failed_gates(monkeypatch,isolated_product):
    import cadforge.production_geometry as geometry
    from cadforge.geometry import BuildResult
    import cadforge.evolve as evolution
    evolution.DEFAULT_DB.touch()
    def fake_build(spec):
        shape=cq.Workplane('XY').box(10,10,10).val()
        assembly=cq.Assembly(name='deceptive');assembly.add(shape,name='chassis')
        return BuildResult(spec,{'chassis':shape},assembly)
    monkeypatch.setattr(geometry,'build_design',fake_build)
    result=run_production(DesignSpec(family='glasses'),isolated_product)
    failed=[g for g in result['engineering']['gates'] if g['status']=='fail']
    assert failed, 'A valid but unrelated box must not satisfy glasses assembly requirements'
    assert any('bearing_material' in g['name'] for g in failed)
    assert any(g['name']=='geometry.required_parts' for g in failed)
    assert result['learning_status']=='no healthy command in current context; nominal recipe fit used'
    assert result['learned_skill_ids']==[]
    assert result['production_ready'] is False


def test_mcp_glasses_routes_through_product_boundary(monkeypatch,tmp_path):
    import cadforge.product as product
    import cadforge.mcpserver as mcp
    calls=[]
    def fake_product(spec,path):
        calls.append((spec,path))
        return {'production_ready':False,'engineering':{'gates':[{'name':'test','status':'blocked'}]},'exports':{},'prebuild_contract_sha256':'test-digest'}
    monkeypatch.setattr(product,'run_production',fake_product)
    monkeypatch.setattr(mcp,'ARTIFACTS',tmp_path)

    result=asyncio.run(mcp.create_server().call_tool('create_camera_glasses',{'parameters':{'lens_width':53}}))
    assert len(calls)==1, 'MCP must not bypass source defaults, learned initialization and prebuild evidence'
    assert calls[0][0].parameters['lens_width']==53
    assert result.is_error is False


@pytest.mark.parametrize('parameters', [
    {'board_length':100}, {'board_width':45}, {'screw_diameter':3},
    {'camera_diameter':14}, {'fastener_diameter':3},
    {'board_height':7,'pi_component_height':8},
])
def test_unsupported_or_conflicting_explicit_dimensions_are_not_ignored(parameters,isolated_product):
    with pytest.raises(ValueError,match='Unsupported|conflicts'):
        run_production(DesignSpec(family='glasses',parameters=parameters),isolated_product)
    assert not isolated_product.exists(), 'Reject inconsistent requirements before generating artifacts'
