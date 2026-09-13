"""Execute our newly generated recipe snapshot after an explicit parameter edit."""
import json,os,subprocess,sys
from pathlib import Path
from cadforge.product import run_production
from cadforge.schema import DesignSpec
from cadforge.handoff import verify_handoff

root=Path(__file__).resolve().parents[1]
out=root/'artifacts/production/packaged-regeneration'
result=run_production(DesignSpec(family='glasses'),out)
assert verify_handoff(result['exports']['manufacturing_manifest'])['integrity_passed']
source=Path(result['exports']['python']).read_text()
source=source.replace('if __name__ == "__main__":',"SPEC['parameters']['lens_width']=53.0\n\nif __name__ == \"__main__\":")
edited=out/'edited-design.py';edited.write_text(source)
code='''import runpy,sys
from pathlib import Path
import cadforge.production_geometry as module
assert Path(module.__file__).resolve().is_relative_to(Path(sys.argv[2]).resolve())
print('Recipe source:',module.__file__)
runpy.run_path(sys.argv[1],run_name='__main__')
'''
env={'PATH':os.environ['PATH'],'PYTHONPATH':str(out/'regeneration/src')}
completed=subprocess.run([sys.executable,'-c',code,str(edited),str(out/'regeneration/src')],
    cwd='/tmp',env=env,capture_output=True,text=True,timeout=90)
(out/'regeneration-execution.log').write_text(completed.stdout+completed.stderr)
assert completed.returncode==0,completed.stderr
new=out/'regenerated';spec=json.loads((new/'design.json').read_text())
assert spec['parameters']['lens_width']==53.0
geometry=json.loads((new/'geometry-screen.json').read_text())
assert geometry['geometry_passed'] and len(geometry['parts'])==6
integrity=verify_handoff(new/'manufacturing-manifest.json');assert integrity['integrity_passed']
receipt={'original_lens_width_mm':result['parameters']['lens_width'],'edited_lens_width_mm':53,
    'packaged_source_used':True,'regenerated_parts':len(geometry['parts']),'geometry_passed':True,
    'integrity':integrity,'production_ready':False,
    'scope':'Known exported source executed with installed dependencies; no clean dependency installation or physical qualification.'}
(out/'regeneration-result.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
