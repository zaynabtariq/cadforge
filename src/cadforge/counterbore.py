"""Conservative counterbores on recognized straight circular Z-through holes.

Faceted mesh operation, not arbitrary freeform drilling or manufacturing approval.
Existing stepped, tapered, blind and oblique bores are intentionally unsupported.
"""
import math
import numpy as np
import trimesh
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from .protected_edit import _recognized_straight


class CounterboreError(ValueError):
    def __init__(self,message,checks=None):
        super().__init__(message);self.checks=checks or []


def _prism(xy,zlo,zhi):
    """Extrude the actual convex polygon of the existing faceted bore."""
    n=len(xy);vertices=np.vstack((np.column_stack((xy,np.full(n,zlo))),np.column_stack((xy,np.full(n,zhi)))))
    faces=[]
    for i in range(n):
        j=(i+1)%n;faces.extend(((i,j,n+j),(i,n+j,n+i)))
    for i in range(1,n-1):faces.extend(((0,i+1,i),(n,n+i,n+i+1)))
    result=trimesh.Trimesh(vertices=vertices,faces=faces,process=False);result.fix_normals()
    return result


def _empty(mesh):return mesh is None or len(mesh.faces)==0


def counterbore(mesh,radius_mm,depth_mm,entry,direction=-1):
    radius=float(radius_mm);depth=float(depth_mm);entry=np.asarray(entry,dtype=float)
    if entry.shape!=(3,) or not np.isfinite(entry).all() or not np.isfinite([radius,depth]).all() or min(radius,depth)<=0:
        raise CounterboreError('Positive finite radius/depth and finite 3D entry required')
    if type(direction) not in (int,float) or direction not in (-1,1):raise CounterboreError('Direction must be -1 from top or +1 from bottom along Z')
    try:features,indices=_recognized_straight(mesh)
    except ValueError as error:raise CounterboreError('Only recognized straight circular Z-through holes are supported: '+str(error)) from error
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
    feature=matching[0];center=np.asarray(feature['center']);bore_radius=feature['radius_mm']
    if radius<=bore_radius+tol:raise CounterboreError('Counterbore radius must exceed existing bore radius and leave an annular floor')
    if np.any(entry[:2]-radius<=lo[:2]+tol) or np.any(entry[:2]+radius>=hi[:2]-tol):raise CounterboreError('Counterbore would touch or cross exterior bounding edge')
    vertices=np.asarray(mesh.vertices)
    radial=np.linalg.norm(vertices[indices,:2]-center,axis=1)
    hole_indices=indices[np.abs(radial-bore_radius)<=max(1e-4,bore_radius*.002)]
    points=vertices[hole_indices]
    lower=np.unique(points[np.abs(points[:,2]-lo[2])<=tol,:2],axis=0)
    upper=np.unique(points[np.abs(points[:,2]-hi[2])<=tol,:2],axis=0)
    if len(lower)<6 or len(lower)!=len(upper) or not np.allclose(lower,upper,rtol=0,atol=tol):raise CounterboreError('Existing bore must have matching straight polygonal entrance and exit rings')
    angles=np.arctan2(lower[:,1]-center[1],lower[:,0]-center[0]);xy=lower[np.argsort(angles)]
    bore_area=abs(float(np.sum(xy[:,0]*np.roll(xy[:,1],-1)-xy[:,1]*np.roll(xy[:,0],-1))/2))
    polygon_area=32*radius**2*math.sin(2*math.pi/64);annular_area=polygon_area-bore_area
    if annular_area<=tol:raise CounterboreError('Counterbore must leave positive annular floor area')
    bottom=plane+direction*depth;overrun=max(1e-4,thickness*1e-5)
    zlo,zhi=sorted((bottom,plane-direction*overrun))
    cutter=trimesh.creation.cylinder(radius=radius,height=zhi-zlo,sections=64)
    cutter.apply_translation([entry[0],entry[1],(zlo+zhi)/2])
    result=trimesh.boolean.difference([mesh,cutter],engine='manifold')
    if _empty(result):raise CounterboreError('Counterbore removed all stock')
    original_void=_prism(xy,float(lo[2])-overrun,float(hi[2])+overrun)
    initial_obstruction=trimesh.boolean.intersection([original_void,result],engine='manifold')
    repair={'initial_intersection_faces':0 if initial_obstruction is None else len(initial_obstruction.faces),'initial_intersection_volume_mm3':0. if initial_obstruction is None else float(np.einsum('ij,ij->i',initial_obstruction.triangles[:,0],np.cross(initial_obstruction.triangles[:,1],initial_obstruction.triangles[:,2])).sum()/6),'operation':'subtract_original_protected_bore_after_composition','applied':not _empty(initial_obstruction)}
    if repair['applied']:
        result=trimesh.boolean.difference([result,original_void],engine='manifold')
    checks=[]
    def check(name,passed,detail):checks.append({'name':'counterbore.'+name,'passed':bool(passed),'detail':detail})
    # Preserve uncut source vertices through kernel float32 roundtrip, only for
    # unique source matches. Newly cut rim/floor vertices are not reconstructed.
    distances,nearest=cKDTree(vertices).query(result.vertices,k=2)
    restore=(distances[:,0]<=tol)&(distances[:,1]>tol)
    updated=np.array(result.vertices,copy=True);updated[restore]=vertices[nearest[restore,0]];result.vertices=updated
    removed=float(mesh.volume-result.volume);expected=annular_area*depth
    check('removed_volume',abs(removed-expected)<=max(1e-5,expected*5e-6),{'removed_mm3':removed,'expected_mm3':expected,'basis':'Actual existing polygon area subtracted from independent 64-gon tool area, multiplied by requested depth'})
    inward=trimesh.creation.cylinder(radius=radius,height=depth,sections=64);inward.apply_translation([entry[0],entry[1],(plane+bottom)/2])
    original_void=_prism(xy,float(lo[2])-overrun,float(hi[2])+overrun)
    required_stock=trimesh.boolean.difference([inward,original_void],engine='manifold')
    missing=trimesh.boolean.difference([required_stock,mesh],engine='manifold')
    check('annular_stock_coverage',not _empty(required_stock) and _empty(missing),{'missing_stock_faces':0 if missing is None else len(missing.faces),'scope':'Annular cutting envelope must contain stock everywhere except the recognized original bore; Boolean representation limits apply'})
    obstructed=trimesh.boolean.intersection([original_void,result],engine='manifold')
    check('original_bore_open',_empty(obstructed),'Full original polygonal through-bore remains material-free')
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
    check('outside_stock_preserved',_empty(added) and _empty(outside),'No representable added material or removed material outside requested tool')
    protected=vertices[hole_indices][(vertices[hole_indices,2]-bottom)*direction>tol]
    distances,_=cKDTree(result.vertices).query(protected) if len(protected) else (np.array([np.inf]),None)
    check('lower_bore_vertices_preserved',bool(len(protected)) and np.all(distances==0),'Original lower-bore boundary vertices retained exactly; new intersection ring defines recess floor')
    check('valid_result',result.is_watertight and result.is_winding_consistent and result.volume>0 and np.isfinite(result.vertices).all() and result.body_count==1 and result.euler_number==mesh.euler_number,'One positive closed connected solid with unchanged through-hole topology')
    if not all(c['passed'] for c in checks):raise CounterboreError('Counterbore failed independent geometry checks; original retained',checks)
    return result,checks,{'kind':'counterbore','entry':[float(entry[0]),float(entry[1]),plane],'direction':int(direction),'radius_mm':radius,'depth_mm':depth,'bottom_z':bottom,'original_bore_radius_mm':bore_radius,'original_bore_polygon_area_mm2':bore_area,'facets':64,'requested_entry':requested_entry.tolist(),'center_roundoff_mm':center_roundoff,'center_roundoff_budget_mm':center_roundoff_budget,'protected_void_repair':repair,'scope':'Recognized straight circular Z-through bore only; numerical faceted operation, not production qualification.'}
