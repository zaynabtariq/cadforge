"""Natural-language planner output to qualified-scope production development CAD."""
from pathlib import Path
import hashlib
import json

def run_production(spec, directory, *, review_inputs=None):
    from dataclasses import asdict,replace
    from .schema import DesignSpec
    from .materials import EYEWEAR_REFERENCE
    from .production_geometry import layout, build_design, export_design
    from .engineering import contract_from_public_layout, assess_geometry
    from .continual import ContinualLearning
    from .evolve import DEFAULT_DB, context
    if spec.family != 'glasses':
        raise ValueError('Production development currently supports the sourced glasses recipe; use robot-link tools for constrained robot edits.')
    requested=dict(spec.parameters)
    supported={'lens_width','lens_height','bridge','temple_length','wall','clearance','lid_thickness',
               'bore_diameter','boss_outer_diameter','camera_bore_diameter','lens_opening_diameter','pi_component_height'}
    fixed={'board_length':65.,'board_width':30.,'screw_diameter':2.5}
    unknown=set(requested)-supported-set(fixed)-{'board_height'}
    if unknown:
        raise ValueError('Unsupported production parameters: '+', '.join(sorted(unknown)))
    for key,value in fixed.items():
        if key in requested and requested[key] != value:
            raise ValueError(f'{key}={requested[key]} conflicts with the fixed sourced hardware requirement {value} mm')
    for key,minimum in {'bore_diameter':2.5,'camera_bore_diameter':2.0}.items():
        if key in requested and requested[key]<minimum:
            raise ValueError(f'{key} cannot admit the fixed {minimum} mm fastener')
    if 'board_height' in requested:
        if 'pi_component_height' in requested and requested['pi_component_height'] != requested['board_height']:
            raise ValueError('board_height conflicts with pi_component_height')
        requested['pi_component_height']=requested['board_height']
    # Reference dimensions are commercial examples, not universal wearer fit.
    parameters = dict(lens_width=52.,lens_height=42.4,bridge=18.,temple_length=145.,wall=2.,clearance=.5,lid_thickness=2.)
    parameters.update({k:v for k,v in requested.items() if k in supported})
    learned_ids=[]
    learning_status='explicit fit parameters' if ('bore_diameter' in parameters or 'boss_outer_diameter' in parameters) else 'unavailable; nominal recipe fit used'
    if 'bore_diameter' not in parameters and 'boss_outer_diameter' not in parameters and DEFAULT_DB.exists():
        store=ContinualLearning(DEFAULT_DB)
        try:
            ctx=context()
            receipt=store.apply_with_provenance('supported_fastener',dict(fastener_diameter=2.5,radial_clearance=.15,min_wall=1.5,bore_diameter=2.5,boss_outer_diameter=2.7),context=ctx)
            rule=receipt['skill_id'];fit=receipt['parameters']
            parameters.update({k:fit[k] for k in ('bore_diameter','boss_outer_diameter')})
            learned_ids.append(rule)
            learning_status='healthy persisted command applied'
        except KeyError:
            learning_status='no healthy command in current context; nominal recipe fit used'
        finally:
            store.close()
    actual=DesignSpec(family='glasses',parameters=parameters)
    out=Path(directory);out.mkdir(parents=True,exist_ok=True)
    public_layout=layout(actual)
    frozen=json.dumps(public_layout,sort_keys=True,indent=2)+'\n'
    (out/'prebuild-layout.json').write_text(frozen)
    contract=contract_from_public_layout(public_layout,wall_mm=parameters['wall'],clearance_mm=parameters['clearance'])
    contract=replace(contract,required_parts=('chassis','pi_lid','camera_lid',
        'cable_guide_0','cable_guide_1','cable_guide_2'))
    if review_inputs is not None:
        from .production_review import supplement_contract
        contract=supplement_contract(contract,review_inputs)
    frozen=json.dumps(asdict(contract),sort_keys=True,indent=2)+'\n'
    (out/'prebuild-contract.json').write_text(frozen)
    candidate=build_design(actual)
    report=assess_geometry(candidate.parts,contract)
    exports=export_design(candidate,out)
    result={'exports':exports,'engineering':report.model_dump(),'production_ready':False,
            'prebuild_contract_sha256':hashlib.sha256(frozen.encode()).hexdigest(),
            'learned_skill_ids':learned_ids,'parameters':parameters,
            'learning_status':learning_status,'requested_parameters':spec.parameters,
            'reference_dimensions':EYEWEAR_REFERENCE}
    (out/'engineering.json').write_text(json.dumps(result,indent=2)+'\n')
    from .handoff import inventory_review_evidence
    inventory_review_evidence(exports['manufacturing_manifest'],{
        'prebuild_contract':out/'prebuild-contract.json',
        'prebuild_layout':out/'prebuild-layout.json',
        'engineering':out/'engineering.json',
        'geometry_screen':exports['geometry_screen'],
    })
    return result
