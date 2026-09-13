"""Read-only dashboard evidence from explicit public development artifact roots."""
import json
from pathlib import Path
from .handoff import verify_handoff


def _latest(paths):
    return max(paths,key=lambda p:p.stat().st_mtime_ns,default=None)


def development_status(workspace):
    root=Path(workspace)/'artifacts';status={}
    started=_latest((root/'access-retrieval-comparison').glob('*/contract.json'))
    comparison=started.parent/'summary.json' if started else None
    if comparison:
        try:
            summary=json.loads(comparison.read_text())
            rows=json.loads((comparison.parent/'results.json').read_text())
            calculated={}
            for arm in ('no_skills','retrieved_affine_adaptation','learned'):
                selected=[r for r in rows if r['arm']==arm]
                if not selected:raise ValueError('Missing comparison arm')
                for row in selected:
                    if row['budget']['used']['cad_candidates']!=len(row['trials']):raise ValueError('Candidate count mismatch')
                    if row['passed']!=bool(row['trials'] and row['trials'][-1].get('passed')):raise ValueError('Outcome mismatch')
                    if row['passed'] and (row.get('error') or not all(row['trials'][-1]['checks'].values())):raise ValueError('Passing result has failed checks')
                calculated[arm]={'passed':sum(r['passed'] for r in selected),'cad_candidates':sum(len(r['trials']) for r in selected)}
                if calculated[arm]!=summary[arm]:raise ValueError('Summary differs from retained trials')
            status['comparison']={'path':str(comparison),'rows':[{'arm':k,**v} for k,v in calculated.items()],
                'scope':summary['limitations'],'checked_against_trials':True}
        except Exception as error:status['comparison']={'path':str(comparison),'error':type(error).__name__+': '+str(error)}
    production=_latest(list((root/'production').glob('*/engineering.json'))+
                       list((root/'mcp-review-check'/'production').glob('*/engineering.json')))
    if production:
        try:
            result=json.loads(production.read_text())
            integrity=verify_handoff(production.parent/'manufacturing-manifest.json')
            counts={s:sum(g['status']==s for g in result['engineering']['gates']) for s in ('pass','fail','blocked')}
            status['production']={'path':str(production),'counts':counts,'integrity_passed':integrity['integrity_passed'],
                'production_ready':False,'blockers':[g['name'] for g in result['engineering']['gates'] if g['status']=='blocked']}
        except Exception as error:status['production']={'path':str(production),'error':type(error).__name__+': '+str(error)}
    costs=[]
    for path in sorted((root/'tool-access-learning').glob('*/summary.json')):
        try:
            data=json.loads(path.read_text());measured={}
            for field,folder in [('discovery_trials','discovery'),('verification_trials','verify'),('comparison_trials','comparison')]:
                if not (path.parent/folder).is_dir():raise ValueError('Missing attempt audit directory')
                count=0
                for audit in (path.parent/folder).glob('*.json'):
                    count+=len(json.loads(audit.read_text())['trials'])
                if field in data and (type(data[field]) is not int or data[field]!=count):raise ValueError('Summary cost differs from retained attempts')
                measured[field]=count
            costs.append({'run':path.parent.name,**measured})
        except Exception as error:costs.append({'run':path.parent.name,'error':type(error).__name__})
    status['tool_access_runs']=costs
    return status
