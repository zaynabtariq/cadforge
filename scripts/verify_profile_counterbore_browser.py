"""Check public exported geometry and untouched source vertices independently."""
import json
from pathlib import Path
import numpy as np
import trimesh
from scipy.spatial import cKDTree
from cadforge.protected_edit import _recognized
p=Path('artifacts/profile-counterbore-browser');record=json.loads((p/'result.json').read_text())
assert record['passed'],record.get('failure')
a=trimesh.load(p/'baseline.stl',force='mesh');b=trimesh.load(p/'edited.stl',force='mesh')
c=record['edit']['command'];center=np.asarray(c['entry'][:2]);radius=c['radius_mm'];floor=c['entry'][2]-c['depth_mm']
features,indices=_recognized(a)
selected=min(features,key=lambda f:np.linalg.norm(np.asarray(f['center'])-center))
upper=a.vertices[(np.abs(a.vertices[:,2]-c['entry'][2])<1e-4)&(np.linalg.norm(a.vertices[:,:2]-center,axis=1)<selected['radius_mm']+.01)]
xy=np.unique(upper[:,:2],axis=0);xy=xy[np.argsort(np.arctan2(xy[:,1]-center[1],xy[:,0]-center[0]))]
old_area=abs(np.sum(xy[:,0]*np.roll(xy[:,1],-1)-xy[:,1]*np.roll(xy[:,0],-1)))/2
expected=(32*radius**2*np.sin(2*np.pi/64)-old_area)*c['depth_mm'];removed=a.volume-b.volume
assert abs(removed-expected)<.02,(removed,expected)
protected=a.vertices[indices];protected=protected[(protected[:,2]<floor-1e-5)|(np.linalg.norm(protected[:,:2]-center,axis=1)>radius+.01)]
distance,_=cKDTree(b.vertices).query(protected)
assert np.all(distance==0),{'lost_protected_vertices':int(np.count_nonzero(distance)),'maximum_distance':float(distance.max())}
assert b.is_watertight and b.is_winding_consistent and b.euler_number==a.euler_number
assert (p/'baseline.stl').read_bytes()==(p/'undone.stl').read_bytes()
result={'actual_removed_mm3':removed,'expected_removed_mm3':expected,'exact_protected_vertices':len(protected),'watertight':True,'undo_exact':True}
(p/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
