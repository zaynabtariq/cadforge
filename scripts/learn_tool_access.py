"""Bounded development learning of tool pockets, with persistent reuse."""
import hashlib,json,uuid
from pathlib import Path
import cadquery as cq
from cadforge.continual import ContinualLearning,Context,Case
from cadforge.access_experiments import access_executor
import cadforge.access_experiments as experiments
import cadforge.engineering as engineering

out=Path('artifacts/tool-access-learning');out.mkdir(parents=True,exist_ok=True)
task=uuid.uuid4().hex;run=out/task;run.mkdir()
ctx=Context('ideal-cad-millimeters','geometric-only; unqualified',{'cadquery':cq.__version__},
    hashlib.sha256(Path(engineering.__file__).read_bytes()+Path(experiments.__file__).read_bytes()).hexdigest(),'tool-access-coupons-v1')
service=ContinualLearning(Path.home()/'.local/share/cadforge/tool-access.sqlite3')
def parameters(d,c,f=0):return {'tool_diameter':d,'radial_clearance':c,'pocket_diameter':d,'family_code':float(f)}
def case(label,p,stage):return Case(task+'-'+label,task+'-'+stage,p,hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest())
discovery=access_executor(run/'discovery',discover=True);verify=access_executor(run/'verify')
learned=False
try:
    identifier=service.latest_id('tool_access_pocket',context=ctx)
except KeyError:
    ids=[service.run_experiment(case(str(i),parameters(d,c),'discovery'),discovery,stage='discovery',context=ctx)
         for i,(d,c) in enumerate([(4.,.1),(4.,.3),(8.,.1),(8.,.3),(6.,.2)])]
    identifier=service.propose_affine('tool_access_pocket','pocket_diameter',('tool_diameter','radial_clearance'),ids)
    service.validate_candidate(identifier,[case('challenge',parameters(7.,.15,1),'challenge')],verify,stage='counterexample',context=ctx)
    service.validate_candidate(identifier,[case('bracket',parameters(5.,.25,1),'transfer-bracket'),case('round',parameters(6.5,.15,2),'transfer-round')],verify,stage='transfer',context=ctx)
    service.promote(identifier);learned=True
probe=parameters(6.5,.25,2)
service.validate_candidate(identifier,[case('monitor',probe,'monitor')],verify,stage='monitor',context=ctx)
applied=service.apply('tool_access_pocket',probe,context=ctx)
measure=access_executor(run/'comparison',discover=True)
# Nearest literal successful discovery script, with the same repair budget.
rows=[json.loads(r[0]) for r in service.db.execute('SELECT payload FROM experiments')]
from dataclasses import asdict
rows=[r for r in rows if r['stage']=='discovery' and r['context']==asdict(ctx)]
nearest=min(rows,key=lambda r:sum((r['inputs'][k]-probe[k])**2 for k in ('tool_diameter','radial_clearance')))
retrieved=probe|{'pocket_diameter':nearest['measurement']['measurements']['pocket_diameter']}
comparisons={}
for name,p in [('no_skills',probe),('retrieved_nearest_script',retrieved),('learned',applied)]:
    result=measure(p,task+'-'+name)
    comparisons[name]={'initial_passed':result.passed,'cad_trials':result.measurements['cad_trials'],'final_pocket_diameter':result.measurements['pocket_diameter']}
summary={'learned_this_run':learned,'skill_id':identifier,'discovery_trials':sum(len(json.loads(p.read_text())['trials']) for p in (run/'discovery').glob('*.json')),
         'comparisons':comparisons,'fitted_commands':service._payload('candidates',identifier)['skill']['commands'],
         'verification_trials':sum(len(json.loads(p.read_text())['trials']) for p in (run/'verify').glob('*.json')),
         'comparison_trials':sum(len(json.loads(p.read_text())['trials']) for p in (run/'comparison').glob('*.json')),
         'scope':'Public development coupons; scalar search comparison, not equal-budget LLM evaluation or production qualification'}
(run/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');service.close();print(json.dumps(summary))
