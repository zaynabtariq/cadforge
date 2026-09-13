"""Check browser-exported sequence against its actual imported baseline."""
import json
from pathlib import Path
import numpy as np
import trimesh
from cadforge.axial_protected_edit import recognize_axial_holes

out=Path('artifacts/axial-sequence-browser')
record=json.loads((out/'browser-result.json').read_text());pv=record['result']['preview']
assert not record.get('error') and not record['errors'] and pv['accepted']
current=Path(pv['parts'][0]['stl_path'])
baseline=current.parents[2]/'versions'/pv['base_version']/current.name
before=trimesh.load(baseline,force='mesh');after=trimesh.load(out/'edited.stl',force='mesh')
_,_,features,indices=recognize_axial_holes(before)
coordinates=set(map(tuple,after.vertices))
assert all(tuple(v) in coordinates for v in before.vertices[indices])
assert after.is_watertight and after.euler_number==before.euler_number
assert abs(after.extents[0]-before.extents[0]-20)<1e-5
assert baseline.read_bytes()==(out/'undone.stl').read_bytes()
checks=[next(c for c in step['checks'] if c['name']=='invariant.preserve_holes') for step in pv['step_outcomes']]
assert len(checks)==2 and all(c['passed'] for c in checks)
result={'holes':len(features),'protected_vertices':len(indices),'final_widening_mm':float(after.extents[0]-before.extents[0]),
        'both_step_invariants_passed':True,'original_protected_vertices_exact':True,'undo_bytes_exact':True,
        'usage':record['result']['usage'],'scope':'Public rotated plate, two protected edits; no strength qualification or new learned-rule promotion.'}
(out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
