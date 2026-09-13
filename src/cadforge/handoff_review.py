"""Fresh engineering review of exported parts against explicit recipe inputs."""
from dataclasses import asdict,replace
import hashlib,json
from pathlib import Path
import cadquery as cq
from .handoff import verify_handoff
from .handoff_geometry import screen_handoff_geometry
from .engineering import contract_from_public_layout,assess_geometry
from .production_geometry import layout
from .production_review import supplement_contract


def review_handoff(manifest_path,expected_spec,output_directory,*,review_inputs=None):
    if expected_spec.family!='glasses':raise ValueError('This sourced review recipe supports glasses only')
    path=Path(manifest_path).resolve()
    integrity=verify_handoff(path)
    if not integrity['integrity_passed']:raise ValueError('Cannot review a package with failed integrity')
    manifest=json.loads(path.read_text())
    if manifest['specification']!=expected_spec.model_dump():
        raise ValueError('Package specification differs from the explicitly requested review specification')
    # Expected geometry constraints come from the independently chosen recipe
    # inputs, not the delivered part bounds or volume measurements.
    parameters=expected_spec.resolved()
    contract=contract_from_public_layout(layout(expected_spec),wall_mm=parameters['wall'],clearance_mm=parameters['clearance'])
    contract=replace(contract,required_parts=('chassis','pi_lid','camera_lid','cable_guide_0','cable_guide_1','cable_guide_2'))
    if review_inputs is not None:contract=supplement_contract(contract,review_inputs)
    out=Path(output_directory).resolve()
    if out.is_relative_to(path.parent):raise ValueError('Fresh review must be outside the original package')
    out.mkdir(parents=True,exist_ok=False)
    encoded=json.dumps(asdict(contract),sort_keys=True,indent=2,allow_nan=False)+'\n'
    (out/'review-contract.json').write_text(encoded)
    receipt={'manifest_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'expected_specification':expected_spec.model_dump(),'contract_sha256':hashlib.sha256(encoded.encode()).hexdigest(),
        'production_ready':False,'source_executed':False}
    try:
        receipt['geometry_screen']=screen_handoff_geometry(path)
        parts={p['name']:cq.importers.importStep(str(path.parent/p['exports']['step'])).val() for p in manifest['parts']}
        receipt['engineering']=assess_geometry(parts,contract).model_dump()
        receipt['package_unchanged']=(hashlib.sha256(path.read_bytes()).hexdigest()==receipt['manifest_sha256']
                                      and verify_handoff(path)['integrity_passed'])
        if not receipt['package_unchanged']:
            receipt['error']='Package changed during review; measurements cannot qualify the final package'
    except Exception as error:
        receipt['error']=f'{type(error).__name__}: {error}'
    receipt['export_consistent']=bool(not receipt.get('error') and receipt.get('package_unchanged')
                                     and receipt.get('geometry_screen',{}).get('geometry_passed'))
    (out/'review-result.json').write_text(json.dumps(receipt,indent=2,allow_nan=False)+'\n')
    return receipt
