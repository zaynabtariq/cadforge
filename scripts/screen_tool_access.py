"""Provisional printed-part access screen; tool dimensions are not supplier data."""
from dataclasses import asdict,replace
from math import sin,cos,radians
from pathlib import Path
import json
from cadforge.schema import DesignSpec
from cadforge.production_geometry import layout,build_design
from cadforge.engineering import ToolAccess,contract_from_public_layout,assess_geometry

out=Path('artifacts/production/tool-access');out.mkdir(parents=True,exist_ok=True)
spec=DesignSpec(family='glasses',parameters={'lens_width':52,'lens_height':42.4,'bridge':18,'temple_length':145,'wall':2,'clearance':.5,'lid_thickness':2})
data=layout(spec);contract=contract_from_public_layout(data,wall_mm=2,clearance_mm=.5)
access=[]
for name in ('pi','camera'):
    rec=data[name];angle=radians(rec['rotation_y'])
    for i,(u,v) in enumerate(rec['holes']):
        for side,z,direction in [('lid',rec['outer_size'][2],1),('base',0,-1)]:
            x,y=u+2.5,v+2.5
            point=(x*cos(angle)+z*sin(angle)+rec['origin'][0],y+rec['origin'][1],-x*sin(angle)+z*cos(angle)+rec['origin'][2])
            axis=(direction*sin(angle),0,direction*cos(angle))
            access.append(ToolAccess(f'{name}_{side}_{i}',point,axis,3,20,
                'Provisional 6 mm diameter, 20 mm straight approach; purchased tool and fastener stack unverified'))
contract=replace(contract,tool_access=tuple(access))
(out/'prebuild-contract.json').write_text(json.dumps(asdict(contract),indent=2)+'\n')
result=assess_geometry(build_design(spec).parts,contract)
gates=[asdict(g) for g in result.gates if g.name.startswith('assembly.tool_access')]
(out/'result.json').write_text(json.dumps({'gates':gates,'production_ready':False,'scope':'Printed-part collision only; assumed tool geometry'},indent=2)+'\n')
print(json.dumps({'tool_access':{status:sum(g['status']==status for g in gates) for status in ('pass','fail','blocked')},'production_ready':False}))
