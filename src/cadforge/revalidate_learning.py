"""Replay all stale local region evidence before atomically publishing a new context."""
import hashlib
import json
from pathlib import Path
import tempfile
import uuid
import numpy as np
import trimesh
from .workspace import PythonWorkspace,_identifier
from .edit_learning import validator_context,record_executed,_store,_save


def _fingerprint(mesh):
    return hashlib.sha256(np.asarray(mesh.vertices).tobytes()+np.asarray(mesh.faces).tobytes()).hexdigest()


def _source(service,evidence):
    folder=service._folder(evidence['session_id'])
    preview=json.loads((folder/'previews'/_identifier(evidence['preview_id'])/'preview.json').read_text())
    if preview.get('session_id')!=evidence['session_id'] or preview.get('preview_id')!=evidence['preview_id']:
        raise ValueError('Retained preview identity mismatch')
    if preview.get('command')!=evidence['command'] or preview.get('selection',{}).get('region')!=evidence['region']:
        raise ValueError('Retained preview and learning evidence disagree')
    part_id=_identifier(preview['selection']['part_id'])
    for path in sorted((folder/'versions').glob('*/'+part_id+'.stl')):
        mesh=trimesh.load(path,force='mesh',process=True)
        if _fingerprint(mesh)==evidence['mesh_sha256']:return path
    raise ValueError('No exact retained input geometry for evidence '+evidence['id'])


def revalidate(service,report_directory):
    report_directory=Path(report_directory);report_directory.mkdir(parents=True,exist_ok=True)
    context=validator_context();run=uuid.uuid4().hex
    with _store(service.region_learning_path) as stored:
        original=json.loads(json.dumps(stored))
    lineage=original.get('revalidations',[])
    generated={r['new_evidence_id'] for r in lineage}
    completed={r['old_evidence_id'] for r in lineage if r['context']==context}
    stale=[e for e in original['evidence'] if e.get('context')!=context
           and e['id'] not in generated and e['id'] not in completed]
    report={'run':run,'validator_context':context,'published':False,'replays':[],'cad_candidates':0,
            'scope':'Re-executed local development evidence only; no imported history or benchmark ingestion'}
    try:
        # Resolve every retained case, including failures, before generating any
        # replacement evidence. A missing counterexample must block publication.
        sources=[_source(service,e) for e in stale]
        with tempfile.TemporaryDirectory(prefix='cadforge-revalidation-') as temporary:
            aggregate=Path(temporary)/'aggregate.json';aggregate.write_text(json.dumps(original))
            for index,(evidence,source) in enumerate(zip(stale,sources)):
                # Every replay starts without a learned priority, so preceding
                # successes cannot suppress later failed candidate attempts.
                runner=PythonWorkspace(service.root,region_learning_path=Path(temporary)/f'isolated-{index}.json')
                state=runner.import_file(source);part=state['parts'][0]
                if len(state['parts'])!=1:raise ValueError('Replay requires a single retained source part')
                selection={'part_id':part['id'],'region':evidence['region']}
                pv=runner.preview(state['id'],evidence['command'],selection)
                if pv.get('budget_exhausted'):raise ValueError('Budget-censored replay cannot establish revalidation')
                if 'repair_trials' not in pv:raise ValueError('Replay did not produce executed candidate evidence')
                mesh=trimesh.load(part['stl_path'],force='mesh',process=True)
                receipt=record_executed(mesh,evidence['command'],evidence['region'],pv['repair_trials'],pv['accepted'],
                    session_id=state['id'],preview_id=pv['preview_id'],hint=pv.get('learning_hint'),
                    error=pv.get('error'),path=aggregate)
                report['cad_candidates']+=len(pv['repair_trials'])
                report['replays'].append({'old_evidence_id':evidence['id'],'new_evidence_id':receipt['evidence_id'],
                    'session_id':state['id'],'preview_id':pv['preview_id'],'accepted':pv['accepted'],
                    'trials':pv['repair_trials'],'learning_status':receipt['status']})
            replacement=json.loads(aggregate.read_text())
            replacement.setdefault('revalidations',[]).extend(
                {'run':run,'context':context,'old_evidence_id':r['old_evidence_id'],
                 'new_evidence_id':r['new_evidence_id']} for r in report['replays'])
            # Compare-and-publish under the same lock used by normal learning.
            # Never overwrite concurrent new user evidence or a changed validator.
            with _store(service.region_learning_path) as current:
                if current!=original or validator_context()!=context:
                    raise ValueError('Learning store or validator changed during replay; nothing published')
                if stale:_save(service.region_learning_path,replacement)
            report['published']=True
    except Exception as error:
        report['error']=f'{type(error).__name__}: {error}'
    (report_directory/(run+'.json')).write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report
