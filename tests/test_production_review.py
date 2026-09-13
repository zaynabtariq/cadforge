import json
import pytest
from cadforge.engineering import EngineeringContract,Envelope,ToolAccess
from cadforge.production_review import supplement_contract


def test_supplement_preserves_hardware_and_records_explicit_tool():
    base=EngineeringContract(components=(Envelope('board',(0,0,0),(10,10,2)),),required_parts=('chassis',))
    tool=ToolAccess('driver',(0,0,20),(0,0,1),3,20,'Declared development tool envelope')
    result=supplement_contract(base,{'tool_access':[tool]})
    assert result.components==base.components and result.required_parts==base.required_parts
    assert result.tool_access==(tool,) and base.tool_access==()


@pytest.mark.parametrize('inputs',[{'components':[]},{'required_parts':[]},{'density_g_cm3':1},
    {'density_g_cm3':True,'material_source':'test'},{'density_g_cm3':float('nan'),'material_source':'test'},
    {'tool_access':[{}]}])
def test_invalid_or_weakening_supplements_rejected(inputs):
    with pytest.raises(ValueError):supplement_contract(EngineeringContract(),inputs)


def test_product_freezes_review_input_before_build(monkeypatch,tmp_path):
    import cadforge.production_geometry as geometry
    from cadforge.product import run_production
    from cadforge.schema import DesignSpec
    tool=ToolAccess('driver',(0,0,20),(0,0,1),3,20,'Declared development tool envelope')
    class StopAfterInspection(Exception):pass
    def inspect(spec):
        contract=json.loads((tmp_path/'prebuild-contract.json').read_text())
        assert contract['tool_access'][0]['name']=='driver'
        assert contract['components'] and contract['mounts'] and contract['required_parts']
        raise StopAfterInspection()
    monkeypatch.setattr(geometry,'build_design',inspect)
    with pytest.raises(StopAfterInspection):
        run_production(DesignSpec(family='glasses'),tmp_path,review_inputs={'tool_access':[tool]})
