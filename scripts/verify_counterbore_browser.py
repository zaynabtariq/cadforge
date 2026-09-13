"""Independent delivered-export checks for the actual browser counterbore run."""
import json
from pathlib import Path
import numpy as np
import trimesh
p=Path('artifacts/counterbore-browser');record=json.loads((p/'result.json').read_text())
assert record['passed'],record.get('failure')
a=trimesh.load(p/'baseline.stl',force='mesh');b=trimesh.load(p/'edited.stl',force='mesh')
c=record['edit']['command'];center=np.asarray(c['entry'][:2]);radius=c['radius_mm'];depth=c['depth_mm']
xy=np.unique(a.vertices[np.linalg.norm(a.vertices[:,:2]-center,axis=1)<2.1,:2],axis=0)
xy=xy[np.argsort(np.arctan2(xy[:,1]-center[1],xy[:,0]-center[0]))]
area=abs(np.sum(xy[:,0]*np.roll(xy[:,1],-1)-xy[:,1]*np.roll(xy[:,0],-1)))/2
expected=(32*radius**2*np.sin(2*np.pi/64)-area)*depth
removed=a.volume-b.volume
assert abs(removed-expected)<.001,(removed,expected)
np.testing.assert_allclose(a.bounds,b.bounds,atol=1e-6)
assert b.is_watertight and b.is_winding_consistent and b.volume>0 and b.euler_number==a.euler_number
assert (p/'baseline.stl').read_bytes()==(p/'undone.stl').read_bytes()
result={'removed_volume_mm3':removed,'independently_expected_mm3':expected,'unchanged_bounds':True,'watertight':True,'undo_exact':True,
        'dimension_rule_id':record['edit']['dimension_rule']['skill_id'],'model_requests':record['edit']['usage']['model_requests']}
(p/'export-verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
