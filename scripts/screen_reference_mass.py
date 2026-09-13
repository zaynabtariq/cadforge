"""Reproducible nominal mass screen; never a complete worn-assembly mass."""
from dataclasses import replace,asdict
import hashlib
import json
from pathlib import Path
from cadforge.engineering import contract_from_public_layout,assess_geometry
from cadforge.materials import HP_MJF_PA12_LEGACY,HARDWARE_MASSES,nominal_screening_inputs
from cadforge.production_geometry import build_design
from cadforge.schema import DesignSpec

ROOT=Path(__file__).resolve().parents[1]
reference=ROOT/'artifacts/production/reference'
output=ROOT/'artifacts/production/mass-audit';output.mkdir(parents=True,exist_ok=True)
spec=DesignSpec(**json.loads((reference/'design.json').read_text()))
layout_path=reference/'prebuild-layout.json'
layout=json.loads(layout_path.read_text())
profile=HP_MJF_PA12_LEGACY
# The contract exists before rebuilding geometry. Never infer it from measurements.
contract=contract_from_public_layout(layout,wall_mm=spec.resolved()['wall'],clearance_mm=spec.resolved()['clearance'],
    density_g_cm3=profile.density_g_cm3,material_source=f'{profile.document_id} {profile.document_date}; legacy nominal screening only')
masses={'pi':HARDWARE_MASSES[0].nominal_mass_g,'camera':HARDWARE_MASSES[1].nominal_mass_g}
contract=replace(contract,components=tuple(replace(c,mass_g=masses[c.name]) for c in contract.components),bom_complete=False)
(output/'prebuild-mass-contract.json').write_text(json.dumps(asdict(contract),indent=2,allow_nan=False))
build=build_design(spec)
report=assess_geometry(build.parts,contract)
parts=[{'part':name,'brep_volume_mm3':shape.Volume(),'nominal_mass_g':shape.Volume()*profile.density_g_cm3/1000} for name,shape in build.parts.items()]
printed=sum(p['nominal_mass_g'] for p in parts)
record={'scope':'Nominal mass of modeled printed parts and two catalog electronics entries only; incomplete installed inventory.',
    'assumptions':nominal_screening_inputs(),'parts':parts,'nominal_printed_mass_g':printed,
    'known_electronics_mass_g':sum(masses.values()),'known_inventory_nominal_mass_g':report.mass_g,
    'unknown_items':[asdict(c) for c in HARDWARE_MASSES if c.nominal_mass_g is None],
    'cg_scope':'Known inventory only; electronics approximated at envelope centers, actual centers of mass and missing inventory unknown.',
    'known_inventory_cg_mm':report.center_of_gravity_mm,
    'input_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [reference/'design.json',layout_path,output/'prebuild-mass-contract.json']},
    'engineering':report.model_dump(),'bom_complete':False,'engineering_ready':False,'actual_mass_measured':False}
(output/'nominal-inventory.json').write_text(json.dumps(record,indent=2,allow_nan=False))
print(json.dumps({k:record[k] for k in ['nominal_printed_mass_g','known_electronics_mass_g','known_inventory_nominal_mass_g','bom_complete','engineering_ready']},indent=2))
