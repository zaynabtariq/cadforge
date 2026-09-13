"""Prospective public development comparison, separate from frozen v1 benchmark."""
import hashlib,json,uuid
from pathlib import Path
import trimesh
from cadforge.workspace import PythonWorkspace
from cadforge.region_edit import deform_region,RegionEditError
from cadforge.edit_learning import recommend,validator_context
out=Path('artifacts/region-contract-transfer')/uuid.uuid4().hex;out.mkdir(parents=True)
contract={'scope':'Public development strategy comparison; not hidden benchmark or general agent comparison',
 'candidate_budget_per_case':3,'cases':[
 {'id':'long-capsule','height':18,'radius':9,'amount':5,'mode':'allow_transition'},
 {'id':'short-capsule','height':8,'radius':7,'amount':4,'mode':'allow_transition'},
 {'id':'rigid-small','height':18,'radius':9,'amount':.1,'mode':'rigid'},
 {'id':'rigid-large','height':18,'radius':9,'amount':5,'mode':'rigid'}],
 'arms':['no_learned_priority','retrieved_transition_script','learned_priority'],
 'validator_context':validator_context()}
encoded=json.dumps(contract,sort_keys=True,indent=2);(out/'contract.json').write_text(encoded)
contract_hash=hashlib.sha256(encoded.encode()).hexdigest()
store=out/'development-learning.json';workspace=PythonWorkspace(out/'sessions',region_learning_path=store)
def selection(state):
 lo,hi=state['parts'][0]['bounds']
 return {'part_id':state['parts'][0]['id'],'region':{'min':[-1,lo[1]-1,lo[2]-1],'max':[hi[0]+1,hi[1]+1,hi[2]+1]}}
discovery=[]
for name,mesh,amount in [('sphere',trimesh.creation.icosphere(subdivisions=2,radius=10),7),('capsule',trimesh.creation.capsule(height=12,radius=8,count=[12,12]),5)]:
 path=out/(name+'.stl');mesh.export(path);state=workspace.import_file(path)
 discovery.append(workspace.preview(state['id'],{'op':'translate','axis':'y','amount_mm':amount},selection(state)))
(out/'discovery.json').write_text(json.dumps(discovery,indent=2))
assert [r['learning']['status'] for r in discovery]==['candidate','promoted']
frozen_store=store.read_bytes()
rows=[]
for case in contract['cases']:
 mesh=trimesh.creation.capsule(height=case['height'],radius=case['radius'],count=[12,12])
 # Canonical STL round-trip represents imported geometry for every arm.
 path=out/(case['id']+'.stl');mesh.export(path);mesh=trimesh.load(path,force='mesh')
 lo,hi=mesh.bounds;region={'min':[-1,lo[1]-1,lo[2]-1],'max':[hi[0]+1,hi[1]+1,hi[2]+1]}
 command={'op':'translate','axis':'y','amount_mm':case['amount'],'translation_mode':case['mode']}
 for arm in contract['arms']:
  cmd=command.copy();hint=None
  if arm=='retrieved_transition_script':cmd['learned_strategy']='interior_transition_power_1'
  if arm=='learned_priority':
   hint=recommend(cmd,path=store)
   if hint['strategy']:cmd['learned_strategy']=hint['strategy']
  try:
   changed,checks=deform_region(mesh.copy(),cmd,region)
   trials=next(c['detail'] for c in checks if c['name']=='repair_trials')
   accepted=True;error=None
   changed.export(out/(case['id']+'-'+arm+'.stl'))
  except RegionEditError as exc:accepted=False;trials=exc.trials;error=str(exc)
  assert len(trials)<=contract['candidate_budget_per_case']
  if case['mode']=='rigid':assert all(t['strategy']=='sharp' for t in trials)
  rows.append({'case':case['id'],'arm':arm,'accepted':accepted,'attempts':len(trials),'trials':trials,'hint':hint,'error':error})
assert store.read_bytes()==frozen_store,'Evaluation must not update learning'
summary={'contract_sha256':contract_hash,'discovery_geometry_executions':len(discovery),'discovery_candidate_trials':sum(r['learning']['attempts'] for r in discovery),'evaluation_updates_learning':False,'model_requests':0,'arms':{arm:{'accepted':sum(r['accepted'] for r in rows if r['arm']==arm),'rejected':sum(not r['accepted'] for r in rows if r['arm']==arm),'candidate_trials':sum(r['attempts'] for r in rows if r['arm']==arm)} for arm in contract['arms']}}
(out/'results.json').write_text(json.dumps({'summary':summary,'rows':rows},indent=2))
print(json.dumps({'path':str(out),**summary},indent=2))
