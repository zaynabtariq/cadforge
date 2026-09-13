"""Compose existing checked workspace operations in an isolated transaction."""
import json
import shutil
import tempfile
import uuid
from pathlib import Path


def _retain_counterexample(service,session_id,fork_state,preview,sequence_id,step_index):
    """Keep exact speculative input in a detached, non-committable audit record.

    This snapshot is never the active workspace state or an Undo ancestor. It
    exists so ordinary local evidence revalidation can resolve its source mesh.
    """
    from .workspace import _write
    folder=service._folder(session_id)
    version=uuid.uuid4().hex;preview_id=uuid.uuid4().hex
    version_dir=folder/'versions'/version;preview_dir=folder/'previews'/preview_id
    version_dir.mkdir();preview_dir.mkdir()
    try:
        parts=[]
        for part in fork_state['parts']:
            destination=version_dir/(part['id']+'.stl')
            shutil.copyfile(part['stl_path'],destination)
            parts.append({**part,'stl_path':str(destination.resolve())})
        lineage={'sequence_preview_id':sequence_id,'step_index':step_index,
                 'scratch_input_version':fork_state['version'],'retained_input_version':version}
        snapshot={**fork_state,'id':session_id,'version':version,'parent_version':None,
                  'parts':parts,'audit_only':True,'composition_lineage':lineage}
        retained={**preview,'session_id':session_id,'preview_id':preview_id,
                  'base_version':version,'parts':parts,'accepted':False,
                  'executed_candidate_accepted':bool(preview['accepted']),
                  'audit_only':True,'composition_lineage':lineage,
                  'audit_note':'Replay record only; original error and trials retained. This record cannot be committed.'}
        _write(version_dir/'state.json',snapshot);_write(preview_dir/'preview.json',retained)
        return {'session_id':session_id,'preview_id':preview_id,'version':version,
                'sequence_preview_id':sequence_id,'step_index':step_index}
    except Exception:
        shutil.rmtree(version_dir,ignore_errors=True);shutil.rmtree(preview_dir,ignore_errors=True)
        raise


def preview_sequence(service,session_id,steps,expected_revision=None,*,planner=None,invariants=None):
    from .workspace import PythonWorkspace,_write
    if not isinstance(steps,list) or not 2<=len(steps)<=8:
        raise ValueError('A composition requires 2 to 8 steps')
    if planner is None and any(not isinstance(step,dict) or set(step)-{'command','selection'} or not isinstance(step.get('command'),dict)
           or not isinstance(step.get('selection',{}),dict) or step['command'].get('op')=='sequence' for step in steps):
        raise ValueError('Each step requires one command and an optional explicit selection; nested sequences are unsupported')
    if planner is not None and any(not isinstance(step,dict) or not isinstance(step.get('request'),str) or not step['request'].strip() for step in steps):
        raise ValueError('Each planned step requires a request')
    # Snapshot caller-owned dictionaries before evaluating any operation.
    steps=json.loads(json.dumps(steps,allow_nan=False))
    with service._lock:
        state=service._document(session_id);folder=service._folder(session_id)
        if expected_revision is not None and expected_revision!=state['revision']:
            raise ValueError('Workspace changed while planning; refresh and request a new preview')
        from .composition_invariants import capture,check
        contracts=capture(state['parts'],[] if invariants is None else invariants)
        preview_id=uuid.uuid4().hex;directory=folder/'previews'/preview_id;directory.mkdir(parents=True)
        record={'preview_id':preview_id,'session_id':session_id,'base_revision':state['revision'],'base_version':state['version'],
            'command':{'op':'sequence','steps':steps,'invariants':[{'kind':c['kind'],'part_id':c['part_id']} for c in contracts]},'selection':{},'accepted':False,'parts':state['parts'],'checks':[],
            'step_outcomes':[],'invariants':contracts,'error':None,'learning_scope':'Speculative successes are not promoted. Executed failures of persistent strategy priorities are retained and quarantined even when the sequence rolls back.'}
        try:
            with tempfile.TemporaryDirectory(prefix='cadforge-composition-') as scratch:
                scratch=Path(scratch);learning=scratch/'learning.json'
                # Reuse the current strategy snapshot without writing speculative
                # outcomes into the user's actual store, even if later steps fail.
                if service.region_learning_path.exists():shutil.copyfile(service.region_learning_path,learning)
                fork=PythonWorkspace(scratch/'sessions',region_learning_path=learning)
                fid=uuid.uuid4().hex;version=uuid.uuid4().hex;ff= fork.root/fid;vd=ff/'versions'/version;vd.mkdir(parents=True)
                parts=[]
                for part in state['parts']:
                    dest=vd/(part['id']+'.stl');shutil.copyfile(part['stl_path'],dest)
                    parts.append({**part,'stl_path':str(dest)})
                fork_state={**state,'id':fid,'version':version,'parent_version':None,'revision':0,'parts':parts,'history':[]}
                _write(ff/'session.json',fork_state);_write(vd/'state.json',fork_state)
                for index,step in enumerate(steps):
                    decision=None
                    if planner is not None:
                        decision=planner(step['request'],step.get('selection',{}),fork_state)
                        record.setdefault('planning',[]).append(decision)
                        if decision.get('clarification'):
                            raise ValueError(f'Step {index+1} needs clarification: {decision["clarification"]}')
                        step['command']=decision['command']
                    pv=fork.preview(fid,step['command'],step.get('selection',{}),expected_revision=index)
                    if pv.get('budget_exhausted'):record['budget_exhausted']=pv['budget_exhausted']
                    # A rollback must not erase an actual counterexample to a
                    # previously persistent priority. Never promote scratch skills
                    # or blame a local strategy for a later shared-invariant failure.
                    hint=pv.get('learning_hint',{})
                    preferred=next((t for t in pv.get('repair_trials',[]) if t['strategy']==hint.get('strategy')),None)
                    if hint.get('skill_id') and preferred and not preferred.get('accepted'):
                        try:
                            import trimesh
                            from .edit_learning import record_executed
                            source=next(p for p in fork_state['parts'] if p['id']==pv['selection']['part_id'])
                            retained=_retain_counterexample(service,session_id,fork_state,pv,preview_id,index+1)
                            pv['retained_counterexample']=retained
                            pv['persistent_learning']=record_executed(
                                trimesh.load(source['stl_path'],force='mesh',process=True),
                                pv['command'],pv['selection']['region'],pv['repair_trials'],pv['accepted'],
                                session_id=session_id,preview_id=retained['preview_id'],
                                hint=hint,error=pv.get('error'),path=service.region_learning_path,quarantine_only=True)
                        except Exception as exc:
                            pv['persistent_learning']={'status':'audit_failed','error':f'{type(exc).__name__}: {exc}',
                                'narrative':'The executed failure is retained in this sequence, but persistent quarantine could not be saved.'}
                    if pv['accepted']:
                        invariant_checks=check(pv['parts'],contracts)
                        pv['checks'].extend(invariant_checks)
                        if not all(c['passed'] for c in invariant_checks):
                            pv['accepted']=False;pv['error']='Cross-step hole preservation invariant failed'
                    outcome={k:pv[k] for k in ('command','selection','accepted','checks','error','repair_trials','created_features','protected_features','learning_hint','persistent_learning','retained_counterexample','budget_exhausted') if k in pv}
                    outcome['input_parts']=[{'id':p['id'],'bounds':p['bounds']} for p in fork_state['parts']]
                    if decision is not None:outcome.update(request=step['request'],explanation=decision.get('explanation'))
                    record['step_outcomes'].append(outcome)
                    record['checks'].append({'name':f'step.{index+1}.accepted','passed':pv['accepted'],'detail':pv['error'] or 'All existing operation checks passed; full results retained in step_outcomes.'})
                    if not pv['accepted']:raise ValueError(f'Step {index+1} rejected: {pv["error"]}')
                    fork_state=fork.commit(fid,pv['preview_id'])
                committed_parts=[]
                for part in fork_state['parts']:
                    dest=directory/(part['id']+'.stl');shutil.copyfile(part['stl_path'],dest)
                    committed_parts.append({**part,'stl_path':str(dest.resolve())})
                record['parts']=committed_parts;record['accepted']=True
        except Exception as exc:
            record['error']=f'{type(exc).__name__}: {exc}'
            record['checks'].append({'name':'sequence.accepted','passed':False,'detail':record['error']})
        if planner is not None and record['accepted']:
            record['command']['steps']=[{'command':step['command'],'selection':step['selection']} for step in record['step_outcomes']]
        _write(directory/'preview.json',record)
        return record
