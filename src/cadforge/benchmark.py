"""Frozen, fail-closed geometry benchmark. Hidden fixtures never enter learner inputs."""
from __future__ import annotations

import hashlib
import json
import os
import random
import secrets
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / 'benchmarks'
PRIVATE = Path.home() / '.cadforge-private' / ROOT.name
FAMILIES = ('glasses', 'enclosure', 'bracket', 'clip')
MODES = ('none', 'retrieved', 'learned')

@dataclass(frozen=True)
class Budget:
    attempts: int = 4
    tool_calls: int = 12
    model_tokens: int = 12000
    wall_seconds: float = 120.0


def _json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, indent=2).encode() + b'\n'


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _params(family: str, rng: random.Random, hidden: bool) -> dict[str, float]:
    p = {'wall': rng.choice([1.6, 2.0, 2.4, 3.0]), 'clearance': rng.choice([0.4, 0.6, 0.8, 1.0])}
    if family in ('enclosure', 'glasses'):
        p.update(board_length=rng.choice([52, 65, 75, 85]), board_width=rng.choice([23, 30, 38, 45]), board_height=rng.choice([6, 8, 10, 12]), camera_diameter=rng.choice([6, 8, 10, 12]))
    if family == 'enclosure':
        p.update(lid_thickness=rng.choice([1.5, 2, 2.5]), screw_diameter=rng.choice([2, 2.5, 3]))
    elif family == 'glasses':
        p.update(lens_width=rng.choice([42, 48, 54]), lens_height=rng.choice([28, 34, 40]), bridge=rng.choice([16, 18, 22]), temple_length=rng.choice([130, 140, 155]))
    elif family == 'bracket':
        p.update(width=rng.choice([30, 40, 55]), height=rng.choice([30, 40, 60]), depth=rng.choice([25, 30, 45]), hole_diameter=rng.choice([3, 5, 7]))
    elif family == 'clip':
        p.update(width=rng.choice([15, 20, 30]), height=rng.choice([20, 25, 35]), gap=rng.choice([5, 8, 12]))
    if hidden:
        # Interpolate dimensions absent from development, while retaining feasible geometry.
        key = {'glasses':'temple_length','enclosure':'board_length','bracket':'width','clip':'height'}[family]
        p[key] += rng.choice([0.25, 0.75, 1.25])
    return p


def make_cases(count_per_family: int, seed: int, hidden: bool = False, composites: int = 0) -> list[dict]:
    rng = random.Random(seed)
    cases = []
    descriptions = {'glasses':'a glasses frame with a Raspberry Pi board housing and a circular camera aperture', 'enclosure':'a Raspberry Pi board enclosure with a circular camera aperture, a lid and screw mounting holes', 'bracket':'a right-angle mounting bracket', 'clip':'a retaining clip'}
    for family in FAMILIES:
        for index in range(count_per_family):
            p = _params(family, rng, hidden)
            values = ', '.join(f'{key}={value:g} mm' for key, value in p.items())
            request = f'Create {descriptions[family]}. Required dimensions: {values}. Return editable source and STEP and STL exports. Preserve all requested dimensions and provide valid solid geometry.'
            cases.append({'id': f'{"hidden" if hidden else "dev"}-{family}-{index:03}', 'family':family, 'request':request, 'expected':p, 'requires':['valid_geometry','constraint_fidelity','editable_source','step_export','stl_export']})
    for index in range(composites):
        pair = [('enclosure','bracket'),('glasses','clip'),('enclosure','clip'),('bracket','clip')][index % 4]
        components = [{'family':family, 'parameters':_params(family, rng, hidden)} for family in pair]
        briefs = '; '.join(f'{c["family"]} with ' + ', '.join(f'{k}={v:g} mm' for k,v in c['parameters'].items()) for c in components)
        cases.append({'id':f'hidden-composite-{index:03}', 'family':'composite', 'request':f'Create an integrated assembly of {briefs}. Join the components using an explicit compatible attachment interface, preserve their functional openings, and return editable assembly source, STEP, and STL.', 'expected_components':components, 'requires':['valid_geometry','constraint_fidelity','editable_source','step_export','stl_export','assembly_interface','functional_openings']})
    return cases


def public_brief(case: dict) -> dict:
    return {key:case[key] for key in ('id','family','request')}


def freeze(private_dir: Path = PRIVATE, public_dir: Path = PUBLIC) -> dict:
    """Create once. Refuse to regenerate or silently update any existing commitment."""
    public_dir.mkdir(parents=True, exist_ok=True)
    private_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    commitment_path = public_dir / 'commitment.json'
    if commitment_path.exists():
        return verify(private_dir, public_dir)
    fixture = private_dir / 'hidden.json'
    if fixture.exists():
        raise RuntimeError('Uncommitted hidden fixture exists; refusing regeneration')
    cases = make_cases(20, secrets.randbits(256), hidden=True, composites=20)
    data = _json(cases)
    with fixture.open('xb') as f:
        f.write(data)
    fixture.chmod(0o600)
    dev = _json(make_cases(6, 41729))
    (public_dir / 'development.json').write_bytes(dev)
    protocol = {'version':1, 'hidden_cases':100, 'development_cases':24, 'modes':list(MODES), 'budget':asdict(Budget()), 'score':'One point only when every required geometry/artifact/constraint check passes. No partial credit.', 'physical_readiness':'Not assessed by geometry benchmark; always false without independent thermal, optical, structural and ergonomic evidence.', 'feedback':'Hidden aggregate counts only; no case feedback or hidden artifact ingestion into learning.', 'execution':'One hidden evaluation per mode; heldout learning disabled; no fixture or evaluator modification after freeze.'}
    (public_dir / 'protocol.json').write_bytes(_json(protocol))
    tracked = [Path(__file__)] + [ROOT/'src/cadforge'/name for name in ('benchmark_reference.py','schema.py')]
    hashes = {str(p.relative_to(ROOT)):_digest(p.read_bytes()) for p in tracked if p.exists()}
    commitment = {'hidden_sha256':_digest(data), 'development_sha256':_digest(dev), 'protocol_sha256':_digest(_json(protocol)), 'source_sha256':hashes, 'hidden_count':100, 'frozen_at_unix':time.time()}
    commitment_path.write_bytes(_json(commitment))
    return commitment


def verify(private_dir: Path = PRIVATE, public_dir: Path = PUBLIC) -> dict:
    c = json.loads((public_dir/'commitment.json').read_text())
    paths = [('hidden_sha256', private_dir/'hidden.json'), ('development_sha256', public_dir/'development.json'), ('protocol_sha256', public_dir/'protocol.json')]
    for key, path in paths:
        if _digest(path.read_bytes()) != c[key]:
            raise RuntimeError(f'Frozen benchmark integrity violation: {path.name}')
    for name, digest in c['source_sha256'].items():
        if _digest((ROOT/name).read_bytes()) != digest:
            raise RuntimeError(f'Frozen checker integrity violation: {name}')
    return c


def check_candidate(case: dict, candidate: dict) -> dict[str, bool]:
    """Validate actual engine geometry and artifacts; never trust an agent's pass flag."""
    import ast
    import cadquery as cq
    from .benchmark_reference import build_design
    from .schema import DesignSpec
    checks = {key:False for key in case['requires']}
    if case['family'] == 'composite':
        return checks
    spec = candidate.get('spec')
    if spec is None:
        return checks
    spec = spec if isinstance(spec, dict) else spec.model_dump()
    params = spec.get('parameters', {})
    checks['constraint_fidelity'] = spec.get('family') == case['family'] and all(isinstance(params.get(k), (int,float)) and abs(params[k]-v) < 1e-8 for k,v in case['expected'].items())
    exports = candidate.get('exports', {})
    if not exports and candidate.get('artifact_dir'):
        base = Path(candidate['artifact_dir'])
        exports = {kind:str(base/('design.'+ext)) for kind,ext in [('python','py'),('step','step'),('stl','stl')]}
    reference = build_design(DesignSpec(family=case['family'], parameters=case['expected']))
    expected = cq.Compound.makeCompound(list(reference.parts.values()))
    try:
        imported = cq.importers.importStep(str(exports['step'])).val()
        solids = imported.Solids()
        checks['step_export'] = bool(imported.isValid() and len(solids) >= len(expected.Solids()) and all(s.Volume()>1e-6 for s in solids))
        reference_bounds, actual_bounds = expected.BoundingBox(), imported.BoundingBox()
        checks['design_envelope'] = all(getattr(actual_bounds,axis+'min') <= getattr(reference_bounds,axis+'min')+1e-4 and getattr(actual_bounds,axis+'max') >= getattr(reference_bounds,axis+'max')-1e-4 and getattr(actual_bounds,axis+'len') <= getattr(reference_bounds,axis+'len')+20 for axis in 'xyz')
        checks['noncollision'] = all(a.intersect(b).Volume()<1e-5 for i,a in enumerate(solids) for b in solids[i+1:])
        for name,probe in reference.probes.items():
            occupied = imported.intersect(probe).Volume()
            if name.endswith('_wall'):
                checks[name] = abs(occupied-probe.Volume())<1e-5 and case['expected']['wall'] >= 1.2
            else:
                checks[name] = occupied<1e-5
                if name == 'component_clearance':
                    checks['minimum_component_clearance'] = imported.distance(probe) >= .2-1e-5
        checks['material_present'] = imported.Volume() >= expected.Volume()*.35
        checks['valid_geometry'] = checks['step_export'] and checks['noncollision']
        if case['family'] == 'enclosure':
            # Mounting-hole diameter must exist in the delivered BRep, not just IR.
            radii = []
            for face in imported.Faces():
                if face.geomType() == 'CYLINDER':
                    from OCP.BRepAdaptor import BRepAdaptor_Surface
                    radii.append(BRepAdaptor_Surface(face.wrapped).Cylinder().Radius())
            checks['screw_mounting_holes'] = sum(abs(r-case['expected']['screw_diameter']/2) < 1e-5 for r in radii) >= 2
    except Exception:
        checks['step_export'] = False
    try:
        tree = ast.parse(Path(exports['python']).read_text())
        assignments = [node for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(t,ast.Name) and t.id == 'SPEC' for t in node.targets)]
        source_spec = ast.literal_eval(assignments[0].value)
        checks['editable_source'] = source_spec == spec and checks['constraint_fidelity']
    except Exception:
        pass
    try:
        import trimesh
        mesh = trimesh.load(str(exports['stl']), force='mesh')
        checks['stl_export'] = bool(mesh.is_watertight and mesh.volume > 0 and abs(mesh.volume-imported.Volume()) / imported.Volume() < .02)
    except Exception:
        pass
    return checks


def evaluate_cases(cases: list[dict], runner: Callable, mode: str, budget: Budget, feedback: bool = False) -> dict:
    successes = 0
    costs = {'attempts':0, 'tool_calls':0, 'model_tokens':0, 'wall_seconds':0.0}
    outcomes = []
    errors = 0
    for case in cases:
        started = time.monotonic()
        try:
            candidate = runner(public_brief(case), mode, budget)
            usage = candidate.get('cost', candidate.get('usage', {}))
            checks = check_candidate(case, candidate)
            complete_usage = all(k in usage for k in ('attempts','tool_calls','model_tokens'))
            valid_usage = complete_usage and all(isinstance(usage[k],(float,int)) and usage[k] >= 0 for k in ('attempts','tool_calls','model_tokens'))
            checks['budget'] = valid_usage and all(usage[k] <= getattr(budget,k) for k in ('attempts','tool_calls','model_tokens')) and time.monotonic()-started <= budget.wall_seconds
            for key in ('attempts','tool_calls','model_tokens'):
                if valid_usage:
                    costs[key] += usage[key]
            success = all(checks.values())
        except Exception:
            errors += 1
            checks = {'execution':False}
            success = False
        costs['wall_seconds'] += time.monotonic()-started
        successes += int(success)
        if feedback:
            outcomes.append({'id':case['id'], 'passed':success, 'checks':checks})
    result = {'mode':mode,'passed':successes,'total':len(cases),'score_percent':100*successes/len(cases) if cases else 0,'cost':costs,'execution_errors':errors,'engineering_ready':False,'physical_validation':'Not performed; geometry checks cannot establish wearable safety.'}
    if feedback:
        result['cases'] = outcomes
    return result


def evaluate_hidden(runner: Callable, modes=MODES, budget: Budget | None = None, private_dir: Path = PRIVATE, public_dir: Path = PUBLIC) -> dict:
    commitment = verify(private_dir, public_dir)
    frozen_budget = Budget(**json.loads((public_dir/'protocol.json').read_text())['budget'])
    if budget is not None and budget != frozen_budget:
        raise ValueError('Budget differs from frozen protocol')
    cases = json.loads((private_dir/'hidden.json').read_text())
    results = []
    for mode in modes:
        if mode not in MODES:
            raise ValueError(f'Unknown baseline: {mode}')
        # Exclusive creation makes interruption or crashes consume the evaluation too.
        with (private_dir/f'evaluated-{mode}.json').open('x') as ledger:
            ledger.write(json.dumps({'started_at':time.time(),'commitment':commitment['hidden_sha256']}))
        result = evaluate_cases(cases, runner, mode, frozen_budget, feedback=False)
        (private_dir/f'result-{mode}.json').write_bytes(_json(result))
        results.append(result)
    return {'commitment':commitment['hidden_sha256'],'results':results,'limitations':['Hidden fixtures are logically separated, not OS-isolated from the orchestrator account.','Budget usage counters are supplied by the instrumented runner; wall time is independently measured.','Composite validation is unsupported and fails closed.','No thermal, optical, structural or ergonomic certification.']}
