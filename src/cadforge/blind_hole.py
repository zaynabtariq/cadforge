"""Depth-defined Z blind drilling on imported closed faceted solids.

The tool is a64-sided inscribed polygon. Removed-volume and floor-area checks
reject incomplete stock engagement rather than silently making a breakout.
"""
import math
import numpy as np
import trimesh


class BlindHoleError(ValueError):
    def __init__(self,message,checks=None):
        super().__init__(message);self.checks=checks or []


def drill_blind_hole(mesh,radius_mm,depth_mm,entry,direction):
    radius=float(radius_mm);depth=float(depth_mm);entry=np.asarray(entry,dtype=float)
    if entry.shape!=(3,) or not np.isfinite(entry).all() or not np.isfinite([radius,depth]).all() or min(radius,depth)<=0:
        raise BlindHoleError('Positive finite radius/depth and a finite3D entry are required')
    if direction not in (-1,1):raise BlindHoleError('Blind drilling direction must be -1(top) or+1(bottom) alongZ')
    if not mesh.is_watertight or not mesh.is_winding_consistent or mesh.volume<=0:
        raise BlindHoleError('Blind drilling requires positively oriented watertight stock')
    lo,hi=np.asarray(mesh.bounds);thickness=hi[2]-lo[2];plane=hi[2] if direction==-1 else lo[2]
    tolerance=max(1e-6,thickness*1e-7)
    if abs(entry[2]-plane)>tolerance:raise BlindHoleError('Entry must lie on the actual exterior top/bottom Z-bound plane for the requested direction')
    if depth>=thickness-tolerance:raise BlindHoleError('Blind depth must remain strictly below stock thickness; through drilling is unsupported')
    if np.any(entry[:2]-radius<=lo[:2]+tolerance) or np.any(entry[:2]+radius>=hi[:2]-tolerance):
        raise BlindHoleError('Hole would touch or cross the stock bounding edge')
    entry=entry.copy();entry[2]=plane
    bottom=plane+direction*depth
    overrun=max(1e-4,thickness*1e-5)
    outside=plane-direction*overrun
    zlo,zhi=sorted((bottom,outside))
    cutter=trimesh.creation.cylinder(radius=radius,height=zhi-zlo,sections=64)
    cutter.apply_translation([entry[0],entry[1],(zlo+zhi)/2])
    result=trimesh.boolean.difference([mesh,cutter],engine='manifold')
    if result is None or not len(result.faces):raise BlindHoleError('Blind cut removed the entire stock or produced no result')
    polygon_area=32*radius**2*math.sin(2*math.pi/64)
    expected=polygon_area*depth;removed=float(mesh.volume-result.volume)
    volume_tolerance=max(1e-5,expected*5e-6)
    checks=[{'name':'blind_hole.full_stock_engagement','passed':bool(abs(removed-expected)<=volume_tolerance),
      'detail':f'Removed {removed:.12g}mm3; independent64-gon area×depth expectation {expected:.12g}mm3; tolerance {volume_tolerance:.12g}. Partial stock, pre-existing voids and breakouts must fail.'}]
    triangles=np.asarray(result.triangles)
    on_floor=np.all(np.abs(triangles[:,:,2]-bottom)<=tolerance,axis=1)
    in_radius=np.linalg.norm(result.triangles_center[:,:2]-entry[:2],axis=1)<=radius+tolerance
    facing=result.face_normals[:,2]*(-direction)>.999999
    floor=on_floor&in_radius&facing
    floor_area=float(result.area_faces[floor].sum())
    checks.append({'name':'blind_hole.requested_floor','passed':bool(floor.any() and abs(floor_area-polygon_area)<=max(1e-5,polygon_area*5e-6)),
      'detail':f'Bottom plane {bottom:.12g}mm = entry {plane:.12g}+direction {direction}×depth {depth:.12g}; measured horizontal floor area {floor_area:.12g}mm2, expected {polygon_area:.12g}mm2.'})
    # Aggregate area/volume tolerances cannot exclude a tiny through passage.
    # Independently require the actual floor patch to be a topological disk.
    disk=False;boundary_loops=0
    if floor.any():
        patch=result.submesh([np.flatnonzero(floor)],append=True,repair=False)
        edges,counts=np.unique(np.sort(patch.edges,axis=1),axis=0,return_counts=True)
        boundary=edges[counts==1]
        if len(boundary):
            from scipy.sparse import coo_matrix
            from scipy.sparse.csgraph import connected_components
            nodes=np.unique(boundary);mapping={int(v):i for i,v in enumerate(nodes)}
            rows=np.array([mapping[int(a)] for a in boundary[:,0]]);cols=np.array([mapping[int(b)] for b in boundary[:,1]])
            graph=coo_matrix((np.ones(2*len(rows)),(np.r_[rows,cols],np.r_[cols,rows])),shape=(len(nodes),len(nodes)))
            boundary_loops=connected_components(graph,directed=False,return_labels=False)
            degree=np.bincount(np.r_[rows,cols],minlength=len(nodes))
            disk=patch.euler_number==1 and patch.body_count==1 and boundary_loops==1 and np.all(degree==2)
    checks.append({'name':'blind_hole.closed_disk_floor','passed':bool(disk),
        'detail':f'Actual bottom-face patch must be one disk with exactly one closed boundary and no inner passage; boundary components={boundary_loops}.'})
    # Also detect representable tiny voids above the floor: subtract stock from
    # the exact inward64-gon tool, independently of aggregate volume tolerance.
    inward=trimesh.creation.cylinder(radius=radius,height=depth,sections=64)
    inward.apply_translation([entry[0],entry[1],(plane+bottom)/2])
    uncovered=trimesh.boolean.difference([inward,mesh],engine='manifold')
    missing_faces=0 if uncovered is None else len(uncovered.faces)
    checks.append({'name':'blind_hole.inward_tool_covered_by_stock','passed':missing_faces==0,
        'detail':f'Exact inward tool minus original stock must have no representable mesh faces; missing-stock faces={missing_faces}. Limited by Boolean kernel numerical representation.'})
    checks.append({'name':'blind_hole.valid_closed_result','passed':bool(result.is_watertight and result.is_winding_consistent and result.volume>0 and np.isfinite(result.vertices).all()),'detail':'Cut result must remain finite, closed, consistently wound and positive-volume.'})
    if not all(check['passed'] for check in checks):raise BlindHoleError('Blind drilling failed stock-engagement or exact-depth geometry checks; original retained',checks)
    feature={'kind':'blind_hole','entry':entry.tolist(),'direction':int(direction),'radius_mm':radius,'depth_mm':depth,'bottom_z':float(bottom),'facets':64,'exterior_overrun_mm':overrun}
    return result,checks,feature
