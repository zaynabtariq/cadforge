from dataclasses import replace
import cadquery as cq
import pytest
from cadforge.engineering import EngineeringContract,ToolAccess,assess_geometry


def test_shaft_clearance_does_not_prove_tool_access():
    # A mounting shaft fits through the narrow neck of a recessed fastening well.
    stock=cq.Workplane('XY').box(20,20,10,centered=False).val()
    shaft=cq.Solid.makeCylinder(1.5,12,cq.Vector(10,10,-1),cq.Vector(0,0,1))
    stock=stock.cut(shaft)
    access=ToolAccess('driver',(10,10,5),(0,0,1),3,12,'Explicit development fixture, not a purchased driver')
    contract=EngineeringContract(tool_access=(access,))
    gate=next(g for g in assess_geometry({'stock':stock},contract).gates if g.name=='assembly.tool_access.driver')
    assert gate.status=='fail' and gate.measured>0
    pocket=cq.Solid.makeCylinder(3.2,6,cq.Vector(10,10,5),cq.Vector(0,0,1))
    corrected=stock.cut(pocket)
    repaired=next(g for g in assess_geometry({'stock':corrected},contract).gates if g.name==gate.name)
    assert repaired.status=='pass'


@pytest.mark.parametrize('changes',[{'axis':(0,0,0)},{'radius_mm':0},{'length_mm':-1},{'source':''},{'origin':(float('nan'),0,0)}])
def test_invalid_access_contract_is_rejected(changes):
    access=replace(ToolAccess('driver',(0,0,0),(0,0,1),3,12,'fixture'),**changes)
    with pytest.raises(ValueError):
        assess_geometry({'stock':cq.Workplane('XY').box(10,10,10).val()},EngineeringContract(tool_access=(access,)))
