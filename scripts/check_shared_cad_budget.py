"""Real development worker/geometry acceptance for shared candidate limits."""
import json,os,sys,uuid
from pathlib import Path
from cadforge.shared_budget import SharedExecutionBudget
from cadforge.evaluation_process import run_worker

root=Path(__file__).resolve().parents[1]
out=root/'artifacts/shared-budget'/uuid.uuid4().hex;out.mkdir(parents=True)
ledger=out/'budget.sqlite3';budget=SharedExecutionBudget(ledger,{'cad_candidates':2})
worker='''import json,sys
from pathlib import Path
import trimesh
from cadforge.shared_budget import SharedExecutionBudget
from cadforge.workspace import PythonWorkspace
request=json.load(sys.stdin);root=Path(request['root']);root.mkdir()
source=root/'stock.stl';trimesh.creation.box(extents=[10,10,10]).export(source)
service=PythonWorkspace(root/'sessions',region_learning_path=root/'learning.json')
state=service.import_file(source)
with SharedExecutionBudget(request['ledger']).activate():
 result=service.preview(state['id'],{'op':'translate','axis':'x','amount_mm':1},{'part_id':state['parts'][0]['id']})
print(json.dumps({'accepted':result['accepted'],'budget_exhausted':result.get('budget_exhausted'),'state_unchanged':service.state(state['id'])==state}))
'''
reports=[]
for i in range(3):
    result=run_worker([sys.executable,'-c',worker],{'root':str(out/str(i)),'ledger':str(ledger)},
        timeout_seconds=20,cwd=out,env={'PATH':os.environ['PATH'],'PYTHONPATH':str(root/'src')},maximum_output_bytes=5000)
    if result.status!='completed':raise RuntimeError('Worker failed: '+result.status)
    reports.append(result.report)
assert [r['accepted'] for r in reports]==[True,True,False]
assert reports[-1]['budget_exhausted']=='cad_candidates'
assert all(r['state_unchanged'] for r in reports)
summary={'workers':reports,'budget':budget.snapshot(),'scope':'Three public box-edit workers sharing two candidate charges; imports are outside candidate budget. No hidden data or model calls.'}
(out/'result.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({'directory':str(out),**summary}))
