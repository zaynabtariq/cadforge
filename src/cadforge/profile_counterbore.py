"""Conservative entrance recesses on recognized coaxial Z-through profiles.

Faceted mesh operation, not arbitrary freeform drilling or manufacturing approval.
Only cylindrical entrance segments are cut; crossing a shoulder or taper rejects.
"""
import math
import numpy as np
import trimesh
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from .protected_edit import _recognized


class CounterboreError(ValueError):
    def __init__(self,message,checks=None):
        super().__init__(message);self.checks=checks or []


def _empty(mesh):return mesh is None or len(mesh.faces)==0


def counterbore(mesh,radius_mm,depth_mm,entry,direction=-1):
    radius=float(radius_mm);depth=float(depth_mm);entry=np.asarray(entry,dtype=float)
    if entry.shape!=(3,) or not np.isfinite(entry).all() or not np.isfinite([radius,depth]).all() or min(radius,depth)<=0:
        raise CounterboreError('Positive finite radius/depth and finite 3D entry required')
    if type(direction) not in (int,float) or direction not in (-1,1):raise CounterboreError('Direction must be -1 from top or +1 from bottom along Z')
    try:features,indices=_recognized(mesh)
    except ValueError as error:raise CounterboreError('Only recognized coaxial Z-through profiles are supported: '+str(error)) from error
    lo,hi=np.asarray(mesh.bounds);thickness=float(hi[2]-lo[2]);tol=max(1e-6,thickness*1e-7)
    plane=float(hi[2] if direction==-1 else lo[2])
    if abs(entry[2]-plane)>tol:raise CounterboreError('Entry must lie on exterior top/bottom stock plane')
    if depth>=thickness-tol:raise CounterboreError('Counterbore depth must leave a lower through-bore section')
    requested_entry=entry.copy()
    # Least-squares circle fits can return signed ~1e-16 mm instead of an
    # exactly representable zero. Canonicalize only coordinates indistinguishable
    # from zero at double precision for this stock scale; never loosen coverage.
    center_roundoff_budget=16*np.finfo(float).eps*max(1.,float(np.max(np.abs(mesh.bounds))))
    entry=entry.copy();entry[:2][np.abs(entry[:2])<=center_roundoff_budget]=0.
    center_roundoff=float(np.linalg.norm(entry-requested_entry))
    matching=[f for f in features if np.linalg.norm(np.asarray(f['center'])-entry[:2])<=tol]
    if len(matching)!=1:raise CounterboreError('Entry must be coaxial with exactly one recognized through hole')
    feature=matching[0];center=np.asarray(feature['center'])
    rings=feature.get('profile',{}).get('rings')
    if not rings:raise CounterboreError('Use straight counterbore operation for an unstepped straight bore')
    ordered=sorted(rings,key=lambda r:direction*r['z'])
    entrance=ordered[0];next_rings=[r for r in ordered if abs(r['z']-entrance['z'])>tol]
    if not next_rings:raise CounterboreError('No independently recognized entrance segment')
    next_z=next_rings[0]['z'];at_next=[r for r in next_rings if abs(r['z']-next_z)<=tol]
    bore_radius=entrance['radius_mm']
    fit_tol=max(1e-4,bore_radius*.002)
    cylindrical=[r for r in at_next if abs(r['radius_mm']-bore_radius)<=fit_tol and np.linalg.norm(np.asarray(r['center'])-entrance['center'])<=fit_tol]
    if len(cylindrical)!=1 or depth>=abs(plane-next_z)-tol:
        raise CounterboreError('Depth must remain strictly within a cylindrical entrance segment; taper or old shoulder crossing unsupported')
    if radius<=bore_radius+tol:raise CounterboreError('Recess radius must exceed entrance radius')
    if np.any(entry[:2]-radius<=lo[:2]+tol) or np.any(entry[:2]+radius>=hi[:2]-tol):raise CounterboreError('Recess crosses exterior bounding edge')
    vertices=np.asarray(mesh.vertices)
    selected=indices[np.linalg.norm(vertices[indices,:2]-center,axis=1)<=feature['radius_mm']+fit_tol]
    points=vertices[selected]
    def ring_points(ring):
        mask=(np.abs(points[:,2]-ring['z'])<=tol)&(np.abs(np.linalg.norm(points[:,:2]-np.asarray(ring['center']),axis=1)-ring['radius_mm'])<=fit_tol)
        return np.unique(points[mask,:2],axis=0)
    upper=ring_points(entrance);lower=ring_points(cylindrical[0])
    if len(lower)<6 or len(lower)!=len(upper) or not np.allclose(lower,upper,rtol=0,atol=tol):raise CounterboreError('Entrance polygon rings must match without taper or twist')
    hole_indices=selected
    angles=np.arctan2(lower[:,1]-center[1],lower[:,0]-center[0]);xy=lower[np.argsort(angles)]
    relative_xy=xy-center
    bore_area=abs(float(np.sum(relative_xy[:,0]*np.roll(relative_xy[:,1],-1)-relative_xy[:,1]*np.roll(relative_xy[:,0],-1))/2))
    polygon_area=32*radius**2*math.sin(2*math.pi/64);annular_area=polygon_area-bore_area
    if annular_area<=tol:raise CounterboreError('Counterbore must leave positive annular floor area')
    bottom=plane+direction*depth;overrun=max(1e-4,thickness*1e-5)
    zlo,zhi=sorted((bottom,plane-direction*overrun))
    cutter=trimesh.creation.cylinder(radius=radius,height=zhi-zlo,sections=64)
    cutter.apply_translation([entry[0],entry[1],(zlo+zhi)/2])
    result=trimesh.boolean.difference([mesh,cutter],engine='manifold')
    if _empty(result):raise CounterboreError('Counterbore removed all stock')
    # Reconstruct the complete existing cavity from its actual inward wall
    # and shoulder triangles, including any lower steps/tapers.
    mask=np.zeros(len(vertices),dtype=bool);mask[selected]=True
    cavity_faces=mesh.faces[np.all(mask[mesh.faces],axis=1)]
    void_vertices=vertices.copy();void_faces=[tuple(f) for f in cavity_faces]
    for z in (float(lo[2]),float(hi[2])):
        endpoint=[r for r in rings if abs(r['z']-z)<=tol]
        if len(endpoint)!=1:raise CounterboreError('Ambiguous profile endpoint')
        xy_end=ring_points(endpoint[0]);angles_end=np.arctan2(xy_end[:,1]-center[1],xy_end[:,0]-center[0]);xy_end=xy_end[np.argsort(angles_end)]
        end_points=np.column_stack((xy_end,np.full(len(xy_end),z)))
        distances,end_indices=cKDTree(vertices).query(end_points)
        if np.max(distances)>tol:raise CounterboreError('Profile endpoint vertices missing')
        for i in range(1,len(end_indices)-1):void_faces.append((int(end_indices[0]),int(end_indices[i]),int(end_indices[i+1])))
    original_void=trimesh.Trimesh(vertices=void_vertices,faces=void_faces,process=True);original_void.remove_unreferenced_vertices();original_void.fix_normals()
    if not original_void.is_watertight or original_void.body_count!=1 or original_void.volume<=0:raise CounterboreError('Complete original protected cavity could not be reconstructed')
    initial_obstruction=trimesh.boolean.intersection([original_void,result],engine='manifold')
    repair={'initial_intersection_faces':0 if initial_obstruction is None else len(initial_obstruction.faces),'initial_intersection_volume_mm3':0. if initial_obstruction is None else float(np.einsum('ij,ij->i',initial_obstruction.triangles[:,0],np.cross(initial_obstruction.triangles[:,1],initial_obstruction.triangles[:,2])).sum()/6),'operation':'subtract_original_protected_bore_after_composition','applied':not _empty(initial_obstruction)}
    if repair['applied']:
        result=trimesh.boolean.difference([result,original_void],engine='manifold')
    checks=[]
    def check(name,passed,detail):checks.append({'name':'profile_counterbore.'+name,'passed':bool(passed),'detail':detail})
    # Preserve uncut source vertices through kernel float32 roundtrip, only for
    # unique source matches. Newly cut rim/floor vertices are not reconstructed.
    distances,nearest=cKDTree(vertices).query(result.vertices,k=2)
    restore=(distances[:,0]<=tol)&(distances[:,1]>tol)
    updated=np.array(result.vertices,copy=True);updated[restore]=vertices[nearest[restore,0]];result.vertices=updated
    post_restore_obstruction=trimesh.boolean.intersection([result,original_void],engine='manifold')
    post_restore_added=trimesh.boolean.difference([result,mesh],engine='manifold')
    repair['post_restore_intersection_faces']=0 if post_restore_obstruction is None else len(post_restore_obstruction.faces)
    repair['post_restore_added_faces']=0 if post_restore_added is None else len(post_restore_added.faces)
    repair['final_operations']=['subtract_complete_original_void','intersect_original_stock']
    # Re-establish protected interfaces after all coordinate restoration. Final
    # unchanged empty-face predicates independently verify these set operations.
    result=trimesh.boolean.difference([result,original_void],engine='manifold')
    result=trimesh.boolean.intersection([result,mesh],engine='manifold')
    removed=float(mesh.volume-result.volume);expected=annular_area*depth
    check('removed_volume',abs(removed-expected)<=max(1e-5,expected*5e-6),{'removed_mm3':removed,'expected_mm3':expected,'basis':'Actual existing polygon area subtracted from independent 64-gon tool area, multiplied by requested depth'})
    inward=trimesh.creation.cylinder(radius=radius,height=depth,sections=64);inward.apply_translation([entry[0],entry[1],(plane+bottom)/2])
    # Complete cavity already reconstructed above.
    required_stock=trimesh.boolean.difference([inward,original_void],engine='manifold')
    missing=trimesh.boolean.difference([required_stock,mesh],engine='manifold')
    check('annular_stock_coverage',not _empty(required_stock) and _empty(missing),{'missing_stock_faces':0 if missing is None else len(missing.faces),'scope':'Annular cutting envelope must contain stock everywhere except the recognized original bore; Boolean representation limits apply'})
    obstructed=trimesh.boolean.intersection([original_void,result],engine='manifold')
    check('original_bore_open',_empty(obstructed),{'scope':'Complete original profile void remains open','faces':0 if obstructed is None else len(obstructed.faces),'volume':0 if obstructed is None else float(np.einsum('ij,ij->i',obstructed.triangles[:,0],np.cross(obstructed.triangles[:,1],obstructed.triangles[:,2])).sum()/6)})
    triangles=np.asarray(result.triangles)
    floor=(np.all(np.abs(triangles[:,:,2]-bottom)<=tol,axis=1)&(np.linalg.norm(result.triangles_center[:,:2]-entry[:2],axis=1)<=radius+tol)&(result.face_normals[:,2]*(-direction)>.999999))
    area=float(result.area_faces[floor].sum());annulus=False;loops=0
    if floor.any():
        patch=result.submesh([np.flatnonzero(floor)],append=True,repair=False)
        edges,counts=np.unique(np.sort(patch.edges,axis=1),axis=0,return_counts=True);boundary=edges[counts==1]
        if len(boundary):
            nodes,inverse=np.unique(boundary,return_inverse=True);pairs=inverse.reshape(-1,2);a,b=pairs.T
            graph=coo_matrix((np.ones(len(a)*2),(np.r_[a,b],np.r_[b,a])),shape=(len(nodes),len(nodes)))
            loops=connected_components(graph,directed=False,return_labels=False)
            annulus=patch.euler_number==0 and patch.body_count==1 and loops==2 and np.all(np.bincount(pairs.ravel(),minlength=len(nodes))==2)
    check('annular_floor',annulus and abs(area-annular_area)<=max(1e-5,annular_area*5e-6),{'bottom_z':bottom,'area_mm2':area,'expected_area_mm2':annular_area,'boundary_loops':int(loops)})
    # BRep-style set differences independently constrain the material change.
    added=trimesh.boolean.difference([result,mesh],engine='manifold')
    lost=trimesh.boolean.difference([mesh,result],engine='manifold')
    outside=trimesh.boolean.difference([lost,cutter],engine='manifold') if not _empty(lost) else None
    check('outside_stock_preserved',_empty(added) and _empty(outside),{'added_faces':0 if added is None else len(added.faces),'outside_faces':0 if outside is None else len(outside.faces)})
    protected_indices=indices[(~np.isin(indices,selected))|((vertices[indices,2]-bottom)*direction>tol)]
    protected=vertices[protected_indices]
    distances,_=cKDTree(result.vertices).query(protected) if len(protected) else (np.array([np.inf]),None)
    check('lower_bore_vertices_preserved',bool(len(protected)) and np.all(distances==0),'Original lower-bore boundary vertices retained exactly; new intersection ring defines recess floor')
    check('valid_result',result.is_watertight and result.is_winding_consistent and result.volume>0 and np.isfinite(result.vertices).all() and result.body_count==1 and result.euler_number==mesh.euler_number,'One positive closed connected solid with unchanged through-hole topology')
    if not all(c['passed'] for c in checks):raise CounterboreError('Counterbore failed independent geometry checks; original retained',checks)
    return result,checks,{'kind':'profile_counterbore','entry':[float(entry[0]),float(entry[1]),plane],'direction':int(direction),'radius_mm':radius,'depth_mm':depth,'bottom_z':bottom,'original_bore_radius_mm':bore_radius,'original_bore_polygon_area_mm2':bore_area,'facets':64,'requested_entry':requested_entry.tolist(),'center_roundoff_mm':center_roundoff,'center_roundoff_budget_mm':center_roundoff_budget,'protected_void_repair':repair,'scope':'Recognized coaxial profile with cylindrical entrance only; depth cannot cross old shoulder or taper. Numerical mesh operation, not production qualification.'}
