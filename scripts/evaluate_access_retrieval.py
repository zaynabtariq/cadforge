"""Public development comparison with full-corpus affine script adaptation.

This is a deterministic retrieval/adaptation control, not an LLM benchmark.
No evaluation observation is written into persistent learning.
"""
import hashlib,json,uuid
from pathlib import Path
from dataclasses import asdict
import numpy as np
import cadquery as cq
from cadforge.continual import ContinualLearning,Context
from cadforge.execution_budget import ExecutionBudget,BudgetExceeded
from cadforge.access_experiments import measure_access
import cadforge.access_experiments as experiments
import cadforge.engineering as engineering


def execute_candidate(parameters,case_index,arm,candidate_index):
    measured=measure_access(parameters)
    measured.validate()
    return measured


def run():
    output=Path('artifacts/access-retrieval-comparison')/uuid.uuid4().hex;output.mkdir(parents=True)
    context=Context('ideal-cad-millimeters','geometric-only; unqualified',{'cadquery':cq.__version__},
        hashlib.sha256(Path(engineering.__file__).read_bytes()+Path(experiments.__file__).read_bytes()).hexdigest(),'tool-access-coupons-v1')
    service=ContinualLearning(Path.home()/'.local/share/cadforge/tool-access.sqlite3')
    try:
        corpus=[json.loads(r[0]) for r in service.db.execute('SELECT payload FROM experiments')]
        corpus=[r for r in corpus if r['stage']=='discovery' and r['context']==asdict(context)
                and 'pocket_diameter' in r['measurement']['measurements']]
        # Full successful-boundary corpus, using the same affine hypothesis class
        # as the learned arm. No literal answer or learned coefficients copied.
        inputs=('tool_diameter','radial_clearance')
        x=np.asarray([[1.]+[r['inputs'][k] for k in inputs] for r in corpus])
        y=np.asarray([r['measurement']['measurements']['pocket_diameter'] for r in corpus])
        if len(corpus)<3 or not np.isfinite(x).all() or not np.isfinite(y).all() or np.linalg.matrix_rank(x)!=3:
            raise ValueError('Insufficient independent finite discovery corpus')
        coefficients=np.linalg.lstsq(x,y,rcond=None)[0]
        contract={'scope':'Public development only; no hidden cases, model calls or persistence of evaluation observations',
            'cad_candidates_per_case_per_arm':20,'context':asdict(context),
            'retrieval':'Full current-context discovery corpus; least-squares affine adaptation, no persistent promotion',
            'corpus_sha256':hashlib.sha256(json.dumps(corpus,sort_keys=True).encode()).hexdigest(),
            'corpus_rows':len(corpus),'adapted_coefficients':coefficients.tolist(),
            'cases':[{'tool_diameter':d,'radial_clearance':c,'family_code':f} for d,c,f in
                     [(4.5,.15,0),(5.5,.25,1),(7.5,.15,2),(6.5,.25,2)]]}
        encoded=json.dumps(contract,sort_keys=True,indent=2);(output/'contract.json').write_text(encoded+'\n')
        (output/'retrieval-corpus.json').write_text(json.dumps(corpus,indent=2)+'\n')
        rows=[]
        for index,case in enumerate(contract['cases']):
            baseline=case|{'pocket_diameter':case['tool_diameter']}
            adapted=case|{'pocket_diameter':float(np.dot([1.]+[case[k] for k in inputs],coefficients))}
            receipt=service.apply_with_provenance('tool_access_pocket',baseline,context=context)
            for arm,parameters in [('no_skills',baseline),('retrieved_affine_adaptation',adapted),('learned',receipt['parameters'])]:
                p=dict(parameters);trials=[];budget=ExecutionBudget({'cad_candidates':20});error=None
                try:
                    while True:
                        budget.charge('cad_candidates')
                        trial={'parameters':dict(p)};trials.append(trial)
                        measured=execute_candidate(p,index,arm,len(trials)-1)
                        trial.update({'passed':measured.passed,'measurements':measured.measurements,'checks':measured.checks})
                        if measured.passed:break
                        p['pocket_diameter']=round(p['pocket_diameter']+.1,8)
                except Exception as exc:error=f'{type(exc).__name__}: {exc}'
                row={'case':index,'arm':arm,'passed':bool(trials and trials[-1].get('passed')),
                     'trials':trials,'budget':budget.snapshot(),'error':error,
                     'skill_id':receipt['skill_id'] if arm=='learned' else None}
                rows.append(row)
                (output/'results.json').write_text(json.dumps(rows,indent=2,allow_nan=False)+'\n')
        summary={arm:{'passed':sum(r['passed'] for r in rows if r['arm']==arm),
                       'cad_candidates':sum(r['budget']['used']['cad_candidates'] for r in rows if r['arm']==arm)}
                 for arm in ('no_skills','retrieved_affine_adaptation','learned')}
        summary['limitations']='Four public cases, deterministic affine adaptation, shared prior discovery cost excluded from online counts; no claim of agent superiority or new unfamiliar-topology transfer.'
        (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        print(json.dumps({'directory':str(output),'summary':summary}))
        return {'directory':str(output),'summary':summary,'model_requests':0,
                'cad_candidates':sum(len(r['trials']) for r in rows)}
    finally:service.close()

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--weave',action='store_true',help='Trace these public development cases to the configured project')
    args=parser.parse_args()
    if args.weave:
        from cadforge.cloud import init_development
        import weave
        client=init_development()
        execute_candidate=weave.op()(execute_candidate)
        result,call=weave.op()(run).call()
        client.flush()
        persisted=client.get_call(call.id)
        receipt={'call_id':call.id,'trace_id':call.trace_id,
                 'server_readback_matches':persisted.output==result}
        (Path(result['directory'])/'weave-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
        if not receipt['server_readback_matches']:raise RuntimeError('Weave readback differs from local result')
        print(json.dumps(receipt))
    else:run()
