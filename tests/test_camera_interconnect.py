import pytest
from cadforge.camera_interconnect import assess_camera_cable,reference_interconnect
from cadforge.production_geometry import layout
from cadforge.schema import DesignSpec

def test_supplied_cable_rejected_and_adapter_family_matches():
    r=reference_interconnect()
    assert r['supplied_standard_standard_assessment']['connector_families']['status']=='fail'
    assert r['assessment']['connector_families']['status']=='pass'
    assert r['assessment']['length']['status']=='blocked'
    assert r['assessment']['physical_qualification']['status']=='blocked'
    assert not r['assessment']['production_ready']

@pytest.mark.parametrize('ends',[('mini','standard'),('standard','mini')])
def test_end_order_does_not_change_family_compatibility(ends):
    assert assess_camera_cable('mini','standard',ends)['connector_families']['status']=='pass'

def test_same_connector_count_is_not_assumed_for_zero():
    assert assess_camera_cable('mini','mini',('mini','standard'))['connector_families']['status']=='fail'

def test_length_has_independent_failure_and_no_release_claim():
    r=assess_camera_cable('mini','standard',('mini','standard'),length_mm=200,required_length_mm=201)
    assert r['length']['status']=='fail'
    r=assess_camera_cable('mini','standard',('mini','standard'),length_mm=300,required_length_mm=201)
    assert r['length']['status']=='pass' and not r['production_ready']

@pytest.mark.parametrize('length',[0,-1,float('nan'),float('inf'),True])
def test_bad_length_rejects(length):
    with pytest.raises(ValueError):assess_camera_cable('mini','standard',('mini','standard'),length_mm=length)

def test_production_layout_carries_source_linked_unresolved_interconnect():
    r=layout(DesignSpec(family='glasses'))['camera_interconnect']
    assert r['selected_length_mm'] is None
    assert r['board_connector']['pins']==22 and r['camera_connector']['pins']==15
