"""Run from outside checkout with PYTHONPATH pointing exclusively to built wheel."""
import json
from pathlib import Path
from fastapi.testclient import TestClient
from cadforge import studio_server as server
from cadforge.runtime_paths import artifact_directory
client=TestClient(server.app)
state=client.post('/api/sample').json()
preview=server.workspace.preview(state['id'],{'op':'translate','axis':'x','amount_mm':5},{'part_id':state['parts'][0]['id']})
assert preview['accepted']
response=client.post(f"/api/sessions/{state['id']}/commit",json={'preview_id':preview['preview_id']})
assert response.status_code==200
export=client.get(f"/api/sessions/{state['id']}/export")
assert export.status_code==200 and len(export.content)>84
project=client.get(f"/api/sessions/{state['id']}/project")
assert project.status_code==200
reopen=client.post('/api/import',files={'file':('saved.cadforge',project.content,'application/json')})
assert reopen.status_code==200,reopen.text
second=client.get(f"/api/sessions/{reopen.json()['id']}/export")
assert export.content==second.content
from cadforge.sequence_planner import plan_sequence
restored=reopen.json();part=restored['parts'][0]
width=part['bounds'][1][0]-part['bounds'][0][0]
sequence=plan_sequence(server.workspace,restored['id'],
    'Make this 1 cm wider then make this 1 cm wider',{'part_id':part['id']},restored['revision'],use_model=False)
assert sequence['preview']['accepted'],sequence
assert [s['command']['target_mm'] for s in sequence['preview']['step_outcomes']]==[width+10,width+20]
server.workspace.commit(restored['id'],sequence['preview']['preview_id'])
server.workspace.undo(restored['id'])
assert client.get(f"/api/sessions/{restored['id']}/export").content==second.content
assert client.get('/').status_code==200
print(json.dumps({'module':server.__file__,'artifact_directory':str(artifact_directory()),'workspace':str(server.DATA),'accepted':True,'project_reopen_byte_identical':True,'sequence_intermediate_targets':[width+10,width+20],'sequence_undo_byte_identical':True,'bundled_ui_served':True,'model_calls':0}))
