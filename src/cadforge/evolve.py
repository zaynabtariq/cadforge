"""Persistent failure -> factor -> challenge -> transfer -> reuse loop."""
from __future__ import annotations
import argparse
from dataclasses import asdict
import hashlib,json,time,uuid
from pathlib import Path
import cadquery as cq
from .continual import ContinualLearning,Context,Case
from .fit_experiments import boundary_executor,verification_executor,measure_coupon

DEFAULT_DB=Path.home()/'.local'/'share'/'cadforge'/'learning.sqlite3'

def context():
    digest=hashlib.sha256(Path(__file__).with_name('fit_experiments.py').read_bytes()).hexdigest()
    return Context('ideal-cad-millimeters','geometric-only; physical manufacturing uncalibrated',{'cadquery':cq.__version__},digest,'fit-coupons-v1')

def _case(task,label,parameters):
    return Case(task+'-'+label,task,parameters,hashlib.sha256((task+label+json.dumps(parameters,sort_keys=True)).encode()).hexdigest())

def evolve(db_path=DEFAULT_DB,output_dir='artifacts/continual',cloud=False):
    started=time.monotonic(); out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    task='task-'+uuid.uuid4().hex[:12]; run_dir=out/task;run_dir.mkdir()
    ctx=context(); service=ContinualLearning(db_path)
    client=None
    wrap=lambda f:f
    def traced(name,fn):
        """Name a learning decision so the trace records why a command changed,
        not only which CAD trials executed."""
        if not cloud: return fn
        import weave
        def call(*args,**kwargs): return fn(*args,**kwargs)
        call.__name__=name; call.__qualname__=name; call.__doc__=fn.__doc__
        return weave.op()(call)
    if cloud:
        from .cloud import init_development
        client=init_development()
        import weave
        wrap=lambda f:weave.op()(f)
    boundary_bore=wrap(boundary_executor('bore_diameter',run_dir/'discovery-bore'))
    boundary_boss=wrap(boundary_executor('boss_outer_diameter',run_dir/'discovery-boss'))
    verify=wrap(verification_executor(run_dir/'verification'))
    # Learning decisions, traced alongside the trials that justify them.
    run_trial=traced('run_experiment',service.run_experiment)
    propose_command=traced('propose_affine_command',service.propose_affine)
    challenge_command=traced('challenge_candidate',service.validate_candidate)
    promote_command=traced('promote_command',service.promote)
    reuse_command=traced('reuse_promoted_command',service.apply)
    select_latest=traced('select_latest_command',service.latest_id)
    initial_audit=service.audit(); learned=[]
    probe={'fastener_diameter':2.5,'radial_clearance':.15,'min_wall':1.5,'bore_diameter':2.5,'boss_outer_diameter':2.7,'family_code':2.}
    try:
        reusable=reuse_command('supported_fastener',probe,context=ctx)
    except KeyError:
        # Factor 1: observe the minimum successful bore for independently varied hardware/clearance.
        ids=[]
        for i,(d,c) in enumerate([(2.,.1),(2.,.3),(4.,.1),(4.,.3),(3.,.2)]):
            p={'fastener_diameter':d,'radial_clearance':c,'min_wall':1.,'bore_diameter':d,'boss_outer_diameter':16.,'family_code':0.}
            ids.append(run_trial(_case(task,f'bore-{i}',p),boundary_bore,stage='discovery',context=ctx))
        bore=propose_command('clearance_bore','bore_diameter',('fastener_diameter','radial_clearance'),ids)
        for stage,points in [('counterexample',[(3.5,.15,1)]),('transfer',[(2.5,.2,1),(3.,.25,2)])]:
            cases=[_case(task+'-'+stage,f'bore-{i}',{'fastener_diameter':d,'radial_clearance':c,'min_wall':1.,'bore_diameter':d,'boss_outer_diameter':16.,'family_code':float(f)}) for i,(d,c,f) in enumerate(points)]
            challenge_command(bore,cases,verify,stage=stage,context=ctx)
        promote_command(bore);learned.append(bore)
        # Factor 2 inherits the bore factor and learns required bearing material.
        ids=[]
        for i,(d,c,w) in enumerate([(2.,.1,1.),(2.,.1,2.),(4.,.3,1.),(4.,.3,2.),(3.,.2,1.5)]):
            p=reuse_command('clearance_bore',{'fastener_diameter':d,'radial_clearance':c,'min_wall':w,'bore_diameter':d,'boss_outer_diameter':16.,'family_code':0.},context=ctx)
            p['boss_outer_diameter']=round(p['bore_diameter']+.2,8)
            ids.append(run_trial(_case(task,f'boss-{i}',p),boundary_boss,stage='discovery',context=ctx))
        boss=propose_command('supported_fastener','boss_outer_diameter',('bore_diameter','min_wall'),ids,parent_ids=(bore,))
        for stage,points in [('counterexample',[(3.5,.15,1.25,1)]),('transfer',[(2.5,.15,1.5,1),(3.,.25,1.75,2)])]:
            cases=[_case(task+'-'+stage,f'boss-{i}',{'fastener_diameter':d,'radial_clearance':c,'min_wall':w,'bore_diameter':d,'boss_outer_diameter':d+.2,'family_code':float(f)}) for i,(d,c,w,f) in enumerate(points)]
            challenge_command(boss,cases,verify,stage=stage,context=ctx)
        promote_command(boss);learned.append(boss)
        reusable=reuse_command('supported_fastener',probe,context=ctx)
    # New task comparison uses identical initial parameters. Both can correct themselves.
    before=measure_coupon(probe)
    monitor_case=_case(task+'-monitor','reuse',probe)
    challenge_command(select_latest('supported_fastener',context=ctx),[monitor_case],verify,stage='monitor',context=ctx)
    after=measure_coupon(reusable)
    # Same scalar search baseline, and a literal script from the smallest training hardware.
    def baseline(p):
        p=dict(p);trials=0
        while trials<80:
            observed=measure_coupon(p);trials+=1
            if observed.passed: return {'passed':True,'cad_trials':trials,'parameters':p}
            if not observed.checks['screw_insertion_clearance']:
                p['bore_diameter']=round(p['bore_diameter']+.1,8)
                p['boss_outer_diameter']=max(p['boss_outer_diameter'],p['bore_diameter']+.2)
            else: p['boss_outer_diameter']=round(p['boss_outer_diameter']+.1,8)
        return {'passed':False,'cad_trials':trials,'parameters':p}
    # Retrieve the nearest executed successful discovery script from the full
    # persisted corpus in the same context; do not cherry-pick a weak script.
    scripts=[]
    for row in service.db.execute('SELECT payload FROM experiments'):
        row=json.loads(row[0])
        if row['stage']=='discovery' and row['context']==asdict(ctx):
            measured=row['measurement']['measurements']
            if 'bore_diameter' in measured and 'boss_outer_diameter' in measured:
                scripts.append(row['inputs']|{k:measured[k] for k in ('bore_diameter','boss_outer_diameter')})
    nearest=min(scripts,key=lambda p:sum((p[k]-probe[k])**2 for k in ('fastener_diameter','radial_clearance','min_wall')))
    retrieved=probe|{k:nearest[k] for k in ('bore_diameter','boss_outer_diameter')}
    comparisons={'no_skills':baseline(probe),'retrieved_nearest_script':baseline(retrieved),
                 'learned_inherited':baseline(reusable)}
    discovery_trials=0
    for p in run_dir.glob('discovery-*/*.json'):
        discovery_trials+=len(json.loads(p.read_text())['trials'])
    summary={'task_id':task,'database':str(Path(db_path).resolve()),'initial_failure_codes':list(before.failure_codes),
       'learned_this_task':learned,'reused_persisted_skills':not learned,'applied_parameters':reusable,
       'comparisons':comparisons,'discovery_cad_trials':discovery_trials,'before_audit':initial_audit,
       'after_audit':service.audit(),'duration_seconds':time.monotonic()-started,
       'context':asdict(ctx),'production_ready':False,
       'evidence_scope':'Executed ideal BRep fit and bearing-wall experiments. Not printer calibration or wearable qualification.'}
    if cloud:
        @wrap
        def continual_task_result(summary:dict): return summary
        continual_task_result(summary)
        client.flush()
    (run_dir/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    (out/'latest.json').write_text(json.dumps(summary,indent=2)+'\n')
    service.close()
    return summary

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--database',type=Path,default=DEFAULT_DB);parser.add_argument('--output',type=Path,default=Path('artifacts/continual'));parser.add_argument('--weave',action='store_true')
    args=parser.parse_args();print(json.dumps(evolve(args.database,args.output,args.weave),indent=2))
