"""Measured repair loop, development discovery, and equal-budget ablations."""
from __future__ import annotations
from dataclasses import asdict
import json
from pathlib import Path
import time
from .schema import DesignSpec
from .geometry import build_design, export_design
from .validation import validate_design
from .skills import SkillLibrary, ParameterCommand, Evidence
from .scheduler import BudgetLedger, BudgetExceeded
from .telemetry import record


def repair(parameters, failures, locked=frozenset()):
    """Same feedback-driven local search in every baseline; no hidden answer values."""
    revised = dict(parameters)
    # Search steps are policy, successful thresholds are discovered by execution.
    if 'minimum_wall' in failures and 'wall' not in locked:
        revised['wall'] = round(revised['wall'] + .4, 6)
    if 'minimum_component_clearance' in failures and 'clearance' not in locked:
        revised['clearance'] = round(revised['clearance'] + .2, 6)
    return revised


def run_design(spec: DesignSpec, output_dir, mode='none', library=None, skill_id=None,
               retrieved=None, max_attempts=4, max_tool_calls=12, locked=None, trace=True,
               initial_weak=False, enhanced=False):
    if mode not in ('none','retrieved','learned'):
        raise ValueError('unknown mode')
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    locked = set(spec.parameters) if locked is None else set(locked)
    params = spec.resolved()
    if initial_weak:
        for key,value in [('wall',.4),('clearance',.05)]:
            if key not in locked:
                params[key]=value
    if mode == 'learned' and library is not None and skill_id:
        proposed = library.compose(skill_id, params)
        params.update({k:v for k,v in proposed.items() if k not in locked})
    elif mode == 'retrieved' and retrieved:
        # A frozen successful script's literal settings, retrieved from development.
        params.update({k:v for k,v in retrieved.items() if k not in locked})
    ledger=BudgetLedger(max_attempts=max_attempts,max_tool_calls=max_tool_calls)
    history=[]; result=None; report=None; exports={}; started=time.monotonic()
    for attempt in range(max_attempts):
        try:
            ledger.consume(attempts=1,tool_calls=2)
        except BudgetExceeded:
            break
        current=DesignSpec(family=spec.family,parameters=params,name=spec.name)
        try:
            builder=build_design
            if enhanced:
                from .enhanced_geometry import build_design as build_enhanced
                builder=build_enhanced
            result=builder(current)
            if enhanced:
                from .enhanced_geometry import validate_enhanced_design
                report=validate_enhanced_design(result)
            else:
                report=validate_design(result)
            failures=[c.name for c in report.checks if not c.passed]
            passed=report.passed
        except Exception as exc:
            failures=[type(exc).__name__+': '+str(exc)]
            passed=False; result=None
        entry={'attempt':attempt+1,'parameters':dict(params),'passed':passed,'failures':failures}
        history.append(entry)
        if trace:
            record(out/'trace.jsonl','attempt',mode=mode,**entry)
        if passed:
            break
        revised=repair(params,failures,locked)
        if revised==params:
            break
        params=revised
    if result is not None:
        try:
            ledger.consume(tool_calls=1)
            exporter=export_design
            if enhanced:
                from .enhanced_geometry import export_design as enhanced_export
                exporter=enhanced_export
            exports=exporter(result,out)
        except BudgetExceeded:
            pass
    cost={k:ledger.snapshot()[k] for k in ('attempts','tool_calls','model_tokens')}
    summary={'mode':mode,'passed':bool(report and report.passed and exports),
             'history':history,'cost':cost,'wall_seconds':time.monotonic()-started,
             'engineering_ready':False,'exports':exports,
             'report': report.model_dump() if report else None}
    if trace:
        (out/'run.json').write_text(json.dumps(summary,indent=2)+'\n')
    return {**summary,'spec':result.spec if result else spec,'build':result}


def discover(output_dir):
    """Two numerical repairs and a child command learned from observed failures.

    Dedicated development probes are separate from the frozen benchmark. No
    hidden cases or result objects are accepted by this API.
    """
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    library=SkillLibrary(); evidence_runs=[]; parents=[]
    experiments=[('wall',DesignSpec(family='bracket',parameters={'wall':.4}),['wall']),
                 ('clearance',DesignSpec(family='enclosure',parameters={'clearance':.05}),['clearance'])]
    for key,spec,mutable in experiments:
        run=run_design(spec,out/key,max_attempts=6,locked=set(spec.parameters)-set(mutable))
        evidence_runs.append(run)
        if not run['passed'] or len(run['history'])<2:
            raise RuntimeError(f'No validated failure-to-success discovery for {key}')
        final=run['history'][-1]['parameters'][key]
        evidence=[Evidence(f'discovery-{key}','development',False,tuple(run['history'][0]['failures']))]
        evidence.append(Evidence(f'discovery-{key}','development',True))
        skill=library.propose(f'ensure_{key}',[ParameterCommand(key,'at_least',final)],evidence)
        regression=[]
        for idx,family in enumerate(('glasses','clip') if key=='wall' else ('glasses','enclosure')):
            params={key:final,'board_length':70+idx*3,'width':33+idx}
            candidate=run_design(DesignSpec(family=family,parameters=params),out/f'{key}-regression-{idx}',max_attempts=1)
            evidence_runs.append(candidate)
            regression.append(Evidence(f'{key}-regression-{idx}','development',candidate['passed'],tuple(candidate['history'][-1]['failures'])))
        library.promote(skill.id,regression);parents.append(skill.id)
    # A combined failure motivates inheritance, not another duplicated literal script.
    failed=run_design(DesignSpec(family='glasses',parameters={'wall':.4,'clearance':.05}),out/'combined-failure',max_attempts=1)
    evidence_runs.append(failed)
    child=library.propose('electronics_shell',[],[Evidence('combined-failure','development',False,tuple(failed['history'][0]['failures']))],parent_ids=parents)
    # Validate proposed composition without allowing unpromoted inference.
    combined=DesignSpec(family='glasses').resolved()
    combined.update(wall=.4,clearance=.05)
    for parent in parents:
        combined=library.compose(parent,combined)
    combined['board_length']=73
    checked=run_design(DesignSpec(family='glasses',parameters=combined),out/'combined-regression',max_attempts=1)
    evidence_runs.append(checked)
    library.promote(child.id,[Evidence('combined-regression','development',checked['passed'],tuple(checked['history'][-1]['failures']))])
    library.save(out/'skills.json')
    retrieved={k:combined[k] for k in ('wall','clearance')}
    (out/'retrieved-script.json').write_text(json.dumps(retrieved,indent=2)+'\n')
    # Retain the actual successful source for the script-retrieval baseline.
    (out/'retrieved-script.py').write_text(Path(checked['exports']['python']).read_text())
    # Transfer probe: all arms see identical initially weak unconstrained geometry.
    transfer={}
    for mode in ('none','retrieved','learned'):
        trial=run_design(DesignSpec(family='glasses',parameters={'board_length':77,'lens_width':51}),out/f'transfer-{mode}',mode=mode,library=library,skill_id=child.id,retrieved=retrieved,initial_weak=True)
        transfer[mode]={k:trial[k] for k in ('passed','cost','history')}
    summary={'discovery_cost':{k:sum(run['cost'][k] for run in evidence_runs) for k in ('attempts','tool_calls','model_tokens')},
             'discovery_wall_seconds':sum(run['wall_seconds'] for run in evidence_runs),
             'promoted_skills':len(library.skills),'composed_skill_id':child.id,'transfer':transfer,
             'limitations':['Discovery is bounded numerical search over a hand-authored repair grammar, not learned model weights.',
                           'Retrieved baseline receives the same successful development settings; final success gains are not assumed.',
                           'Transfer probes are development evidence, never hidden benchmark results.']}
    (out/'discovery.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary
