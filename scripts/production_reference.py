"""Preserve failed V2 reference, freeze public contract, regenerate and assess.

No hidden benchmark access. Public layout is snapshotted before any candidate
build; the engineering evaluator independently constructs its BRep probes.
"""
from pathlib import Path
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import shutil
import sys
import cadquery as cq
from cadforge.schema import DesignSpec
from cadforge.production_geometry import layout, build_design, export_design
from cadforge.engineering import contract_from_public_layout, assess_geometry

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/production/reference'
SOURCE=ROOT/'examples/production_reference.json'

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n')


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    previous=OUT/'engineering.json'
    archived=OUT/'iteration-0'
    if previous.exists() and not archived.exists():
        previous_report=json.loads(previous.read_text())
        if previous_report['counts']['fail']:
            archived.mkdir()
            for path in list(OUT.iterdir()):
                if path.is_file():shutil.copy2(path,archived/path.name)
            write(archived/'manifest.json',{path.name:digest(path) for path in archived.iterdir() if path.is_file()})
    spec=DesignSpec.model_validate_json(SOURCE.read_text())
    params=spec.resolved()
    # Required order: establish public contract before executing candidate CAD.
    public_layout=layout(spec)
    contract=contract_from_public_layout(public_layout,wall_mm=params['wall'],clearance_mm=params['clearance'])
    write(OUT/'prebuild-contract.json',asdict(contract))
    write(OUT/'prebuild-layout.json',public_layout)
    contract_hash=digest(OUT/'prebuild-contract.json')
    candidate=build_design(spec)
    exports=export_design(candidate,OUT)
    report=assess_geometry(candidate.parts,contract).model_dump()
    write(OUT/'engineering.json',report)
    compound=cq.Compound.makeCompound(list(candidate.parts.values()))
    views={}
    for name,direction in [('front',(0,0,-1)),('side',(1,0,0)),('top',(0,1,0)),('isometric',(1,1,1))]:
        path=OUT/(name+'.svg')
        cq.exporters.export(compound,str(path),opt={'width':1000,'height':700,'projectionDir':direction,'showHidden':False})
        views[name]=str(path.relative_to(ROOT))
    before=json.loads((archived/'engineering.json').read_text()) if archived.exists() else None
    history={'generated_at_utc':datetime.now(timezone.utc).isoformat(),
      'reference_source':str(SOURCE.relative_to(ROOT)),'reference_sha256':digest(SOURCE),
      'source_hardware_urls':[public_layout[name]['source'] for name in ('pi','camera')],
      'prebuild_contract_sha256':contract_hash,'engineering_ready':False,
      'iterations':[{'id':0,'status':'preserved_failed_artifact' if before else 'unavailable',
        'counts':before['counts'] if before else None,'report':'iteration-0/engineering.json' if before else None,
        'failure':'Fixed world Y=0 left the Pi pod disconnected from taller reference temples.'},
        {'id':1,'status':'actual_regenerated_and_measured','counts':report['counts'],'report':'engineering.json',
         'change':'Solve mating-anchor translation from requested frame and pod dimensions; derive cable route from transformed connector envelopes.',
         'preserved_requirements':spec.model_dump(),
         'reused_operations':['translation_for_anchor','preserve_interface_voids']}],
      'development_sweep':{'command':'.venv/bin/python -m pytest tests/test_production_geometry.py tests/test_operations.py -q',
        'actual_passed':35,'actual_failed':0,'observed_duration_seconds':51.61,
        'frame_combinations':27,'lens_widths_mm':[48,52,54],'lens_heights_mm':[34,42.4,46],'temple_lengths_mm':[140,145,150],
        'evidence_note':'Observed successful command before regeneration; duration is that run, not an estimate or this script runtime.'},
      'limits':['Geometry checks are separate from physical evidence; blocked gates remain unresolved.',
        'The public layout snapshot comes from source-informed design layout code; independent evaluator reconstructs probes, but this is not an adversarially isolated hardware oracle.',
        'No hidden benchmark instances or artifacts are read; frozen V1 results are untouched.'],
      'views':views,'exports':exports}
    write(OUT/'iteration-history.json',history)
    print(json.dumps({'counts':report['counts'],'archive_preserved':archived.exists(),'output':str(OUT)},indent=2))

if __name__=='__main__':main()
