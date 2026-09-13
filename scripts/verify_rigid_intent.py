"""Actual language-to-CAD development check; retains immutable per-run evidence."""
import json,uuid,os
from pathlib import Path
import trimesh
from cadforge.workspace import PythonWorkspace
from cadforge.edit_planner import plan_edit
from cadforge.studio_server import trace_edit
out=Path('artifacts/rigid-intent')/uuid.uuid4().hex
out.mkdir(parents=True)
source=out/'sphere.stl';trimesh.creation.icosphere(subdivisions=2,radius=10).export(source)
workspace=PythonWorkspace(out/'sessions',region_learning_path=out/'learning.json')
state=workspace.import_file(source)
original=workspace.export_path(state['id']).read_bytes()
selection={'part_id':state['parts'][0]['id'],'region':{'min':[-1,-11,-11],'max':[11,11,11]}}
@trace_edit
def actual_request(request):
    decision=plan_edit(request,selection,state,use_model=True)
    if decision.get('command') is None:return decision
    return decision|{'preview':workspace.preview(state['id'],decision['command'],selection)}
records=[actual_request(p) for p in ['Move this rigidly 7 mm backward','Move this rigidly 0.1 mm backward']]
(out/'result.json').write_text(json.dumps(records,indent=2))
assert records[0]['command']['translation_mode']=='rigid'
assert records[0]['preview']['accepted'] is False
assert records[1]['preview']['accepted'] is True
assert all(r['planner'].startswith('pydantic_ai') for r in records)
assert workspace.export_path(state['id']).read_bytes()==original
(out/'result.json').write_text(json.dumps(records,indent=2))
print(json.dumps({'path':str(out),'accepted':[r['preview']['accepted'] for r in records],'usage':[r['usage'] for r in records]},indent=2))
