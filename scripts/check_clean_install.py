"""Verify installed extras and native CAD without importing checkout modules."""
import asyncio,json,sys
from pathlib import Path
import cadforge, weave, pydantic_ai
from cadforge.mcpserver import create_server
from cadforge.edit_planner import plan_edit
from pydantic_ai.models.test import TestModel
from cadforge.production_geometry import build_design,layout,export_design
from cadforge.engineering import assess_geometry,contract_from_public_layout
from cadforge.schema import DesignSpec
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
assert str(Path(cadforge.__file__).resolve()).startswith(str(Path(sys.prefix).resolve()))
model=TestModel(custom_output_args={'command':{'op':'translate','axis':'x','amount_mm':1,'translation_mode':'allow_transition'},'explanation':'move','clarification':None})
plan=plan_edit('Move this rigidly 1 mm right',{'part_id':'p'}, {'parts':[{'id':'p','bounds':[[0,0,0],[10,10,10]]}]},use_model=True,model=model)
assert plan['command']['translation_mode']=='rigid'
tools=asyncio.run(create_server().list_tools())
assert len(tools)>0
spec=DesignSpec(family='glasses');data=layout(spec)
contract=contract_from_public_layout(data,wall_mm=spec.resolved()['wall'],clearance_mm=spec.resolved()['clearance'])
build=build_design(spec);report=assess_geometry(build.parts,contract)
assert not [gate for gate in report.gates if gate.status=='fail']
exports=export_design(build,out/'design')
result={'module':cadforge.__file__,'python':sys.version,'mcp_tool_count':len(tools),'typed_model_test':'TestModel only; no remote inference','weave_imported':True,'exports':exports,'engineering':report.model_dump(),'physical_qualification':False}
(out/'result.json').write_text(json.dumps(result,indent=2))
print(json.dumps({'module':cadforge.__file__,'mcp_tool_count':len(tools),'engineering_counts':report.model_dump()['counts']}))
