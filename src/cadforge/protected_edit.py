"""Conservative imported-mesh widening with recognized Z-through-hole protection.

Feature recognition is geometric, not recovered CAD history. The protected
support band is a user-specified geometric assumption, not a strength guarantee.
"""
import numpy as np
import trimesh
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from .region_edit import _validate, _intersecting_pairs


def _recognized_straight(mesh):
    if not isinstance(mesh,trimesh.Trimesh) or not mesh.is_watertight or not mesh.is_winding_consistent or mesh.volume<=0:
        raise ValueError('A closed, positively oriented mesh is required')
    if len(mesh.faces)>100000:raise ValueError('Protected editing is limited to100000 triangles')
    if mesh.body_count!=1:raise ValueError('Protected editing requires one connected component')
    vertical=np.flatnonzero(np.abs(mesh.face_normals[:,2])<1e-6)
    if not len(vertical):raise ValueError('No Z-normal through-hole wall patches recognized')
    adjacency=mesh.face_adjacency
    selected=np.zeros(len(mesh.faces),dtype=bool);selected[vertical]=True
    pairs=adjacency[np.all(selected[adjacency],axis=1)]
    mapping=np.full(len(mesh.faces),-1,dtype=int);mapping[vertical]=np.arange(len(vertical))
    if len(pairs):
        rows=mapping[pairs[:,0]];cols=mapping[pairs[:,1]]
        graph=coo_matrix((np.ones(2*len(rows)),(np.r_[rows,cols],np.r_[cols,rows])),shape=(len(vertical),len(vertical)))
    else:graph=coo_matrix((len(vertical),len(vertical)))
    count,labels=connected_components(graph,directed=False)
    bounds=mesh.bounds;span=bounds[1,2]-bounds[0,2];features=[];all_vertices=[]
    tolerance=max(1e-5,span*1e-6)
    for group in range(count):
        faces=vertical[labels==group];indices=np.unique(mesh.faces[faces]);points=np.asarray(mesh.vertices)[indices]
        if len(faces)<6 or len(points)<6:continue
        if abs(points[:,2].min()-bounds[0,2])>tolerance or abs(points[:,2].max()-bounds[1,2])>tolerance:continue
        xy=points[:,:2];matrix=np.column_stack((2*xy,np.ones(len(xy))))
        coefficients,_,rank,_=np.linalg.lstsq(matrix,np.einsum('ij,ij->i',xy,xy),rcond=None)
        if rank<3:continue
        center=coefficients[:2];radii=np.linalg.norm(xy-center,axis=1);radius=float(radii.mean())
        if radius<=1e-6 or np.max(np.abs(radii-radius))>max(1e-4,radius*.002):continue
        radial=mesh.triangles_center[faces,:2]-center
        cosine=np.einsum('ij,ij->i',radial,mesh.face_normals[faces,:2])/np.linalg.norm(radial,axis=1)
        if not np.all(cosine<-.9):continue  # excludes an outside cylindrical skin
        angles=np.unique(np.round(np.arctan2(xy[:,1]-center[1],xy[:,0]-center[0]),9));angles.sort()
        if np.max(np.diff(np.r_[angles,angles[0]+2*np.pi]))>np.pi/2:continue
        features.append({'center':center.tolist(),'radius_mm':radius,'z_min':float(points[:,2].min()),'z_max':float(points[:,2].max()),'fit_residual_mm':float(np.max(np.abs(radii-radius))),'protected_vertex_count':len(indices)})
        all_vertices.extend(indices.tolist())
    if not features:raise ValueError('No complete circular Z-through holes recognized; blind, slanted and ambiguous channels unsupported')
    if mesh.euler_number!=2-2*len(features):
        raise ValueError('Recognized hole count does not explain mesh genus; unrecognized channels or topology remain')
    return features,np.unique(all_vertices)



def _recognized(mesh):
    try:
        return _recognized_straight(mesh)
    except ValueError:
        # A straight-only rejection never becomes a relaxed straight acceptance.
        # The independent profile recognizer requires full-height coaxial rings,
        # connected wall/shoulder topology, inward normals and matching genus.
        from .profile_recognition import recognize_coaxial_holes
        return recognize_coaxial_holes(mesh)


def _split_at_band(mesh,axis,lower,upper):
    """Split spanning triangles at affine-map breakpoints before moving rails.

    Original vertices retain their exact coordinates and indices. Only cut-plane
    vertices and corresponding triangles are introduced, preserving bore facets.
    """
    vertices=np.asarray(mesh.vertices).tolist();faces=[]
    lookup={tuple(np.round(v,11)):i for i,v in enumerate(vertices)}
    def clip(poly,plane,keep_lower):
        out=[]
        for i,start in enumerate(poly):
            end=poly[(i+1)%len(poly)]
            da=start[axis]-plane;db=end[axis]-plane
            ia=da<=0 if keep_lower else da>=0
            ib=db<=0 if keep_lower else db>=0
            if ia:out.append(start)
            if ia!=ib:
                point=start+(end-start)*(-da/(db-da));point[axis]=plane;out.append(point)
        unique=[]
        for point in out:
            if not unique or np.linalg.norm(point-unique[-1])>1e-10:unique.append(point)
        if len(unique)>1 and np.linalg.norm(unique[0]-unique[-1])<=1e-10:unique.pop()
        return unique
    def add(poly):
        if len(poly)<3:return
        indices=[]
        for point in poly:
            key=tuple(np.round(point,11))
            if key not in lookup:lookup[key]=len(vertices);vertices.append(point.tolist())
            indices.append(lookup[key])
        for j in range(1,len(indices)-1):
            a,b,c=indices[0],indices[j],indices[j+1]
            if len({a,b,c})<3:continue
            points=np.asarray([vertices[a],vertices[b],vertices[c]])
            if np.linalg.norm(np.cross(points[1]-points[0],points[2]-points[0]))>1e-12:faces.append([a,b,c])
    for triangle in np.asarray(mesh.triangles):
        add(clip(list(triangle),lower,True))
        middle=clip(list(triangle),lower,False)
        if middle:add(clip(middle,upper,True))
        add(clip(list(triangle),upper,False))
    return trimesh.Trimesh(vertices=vertices,faces=faces,process=False)


def _numerical_check_mesh(mesh):
    # Protected-tool intersection normalization only. The SAT projection tolerance
    # becomes1e-13mm, while normal/cross-axis cutoffs scale by different powers.
    # This differs from raw-mm SAT policy and is not an exact-predicate guarantee.
    # Area, volume and face-orientation checks must never use this scaled mesh.
    result=mesh.copy();result.vertices=np.asarray(result.vertices)*1000
    return result

def resize_preserving_holes(mesh,axis,target_mm,min_wall_mm=1):
    axis={'x':0,'y':1}.get(axis,axis)
    if axis not in (0,1):raise ValueError('Protected widening supports x or y only, for Z-normal through holes')
    target=float(target_mm);wall=float(min_wall_mm)
    if not np.isfinite([target,wall]).all() or wall<=0:raise ValueError('Finite target and positive min_wall_mm are required')
    features,hole_indices=_recognized(mesh)
    if _intersecting_pairs(_numerical_check_mesh(mesh),np.arange(len(mesh.faces))) is not None:raise ValueError('Input has detected triangle intersections')
    vertices=np.asarray(mesh.vertices).copy();lo=float(vertices[:,axis].min());hi=float(vertices[:,axis].max());current=hi-lo
    if target<=current+1e-8:raise ValueError('Only widening beyond the current extent is supported; shrinking rejected')
    lower=min(f['center'][axis]-f['radius_mm'] for f in features)-wall
    upper=max(f['center'][axis]+f['radius_mm'] for f in features)+wall
    # Cut planes must survive binary STL serialization across inherited edits.
    # Round outward by one float32 step, enlarging rather than reducing the
    # required support band. All geometry validators remain unchanged.
    lower=float(np.nextafter(np.float32(lower),np.float32(-np.inf)))
    upper=float(np.nextafter(np.float32(upper),np.float32(np.inf)))
    left=lower-lo;right=hi-upper
    if min(left,right)<=1e-6:raise ValueError('Insufficient outer rail room beyond the protected holes and support band')
    extension=(target-current)/2
    stretches=((left+extension)/left,(right+extension)/right)
    if max(stretches)>4:raise ValueError('Requested rail deformation exceeds the conservative4x stretch guard')
    original=mesh
    mesh=_split_at_band(mesh,axis,lower,upper)
    if not mesh.is_watertight or mesh.euler_number!=original.euler_number:
        raise ValueError('Band-plane subdivision did not preserve closed topology')
    vertices=np.asarray(mesh.vertices).copy()
    before=vertices.copy();left_mask=vertices[:,axis]<lower;right_mask=vertices[:,axis]>upper
    vertices[left_mask,axis]=lower+(vertices[left_mask,axis]-lower)*stretches[0]
    vertices[right_mask,axis]=upper+(vertices[right_mask,axis]-upper)*stretches[1]
    changed=left_mask|right_mask
    candidate=trimesh.Trimesh(vertices=vertices,faces=mesh.faces.copy(),process=False)
    # Physical area, volume and orientation checks stay in original mm units.
    # Only the intersection predicate uses this tool's explicit normalization.
    checks=[item for item in _validate(mesh,candidate,changed) if item['name']!='no_detected_triangle_intersection']
    for item in checks:
        if item['name']=='triangle_indices_preserved':
            item['name']='subdivided_triangle_indices_preserved'
            item['detail']='Band-plane subdivision changes source topology; the subdivided indices remain fixed during rail movement.'
    if all(item['passed'] for item in checks):
        touched=np.flatnonzero(np.any(changed[candidate.faces],axis=1))
        hit=_intersecting_pairs(_numerical_check_mesh(candidate),touched)
        checks.append({'name':'no_detected_triangle_intersection','passed':hit is None,'detail':f'Protected-tool SAT at1000x coordinate scale; intersection={hit}. Projection and axis-degeneracy cutoffs scale differently; this is a distinct numerical policy, not exact-predicate certification. Physical area/volume floors remain unscaled.'})
    def check(name,passed,detail):checks.append({'name':name,'passed':bool(passed),'detail':detail})
    check('original_hole_vertices_retained',np.array_equal(vertices[hole_indices],np.asarray(original.vertices)[hole_indices]),'Original protected vertices retain indices and exact coordinates despite rail subdivision.')
    check('protected_hole_vertices_exact',np.array_equal(vertices[hole_indices],before[hole_indices]),'All recognized cylindrical-wall vertex coordinates retained bitwise.')
    check('protected_support_band_exact',np.array_equal(vertices[~changed],before[~changed]),f'Axis band[{lower},{upper}] includes every recognized hole plus assumed support margin {wall}mm.')
    check('z_coordinates_exact',np.array_equal(vertices[:,2],before[:,2]),'Thickness coordinates unchanged for every vertex.')
    check('requested_extent',np.isclose(np.ptp(vertices[:,axis]),target,rtol=1e-9,atol=1e-8),f'Requested {target}mm; actual {np.ptp(vertices[:,axis])}mm.')
    after,_=_recognized(candidate)
    before_sorted=sorted(features,key=lambda f:tuple(f['center']));after_sorted=sorted(after,key=lambda f:tuple(f['center']))
    invariant=len(after_sorted)==len(before_sorted) and all(np.allclose(a['center'],b['center'],rtol=0,atol=1e-8) and abs(a['radius_mm']-b['radius_mm'])<1e-8 for a,b in zip(before_sorted,after_sorted))
    check('recognized_axes_and_radii_preserved',invariant,'Independent repeat recognition retains hole centers and maximum profile radii.')
    profiles_preserved=True
    for prior,current_feature in zip(before_sorted,after_sorted):
        if 'profile' not in prior:continue
        old_rings=prior['profile']['rings'];new_rings=current_feature.get('profile',{}).get('rings',[])
        if len(old_rings)!=len(new_rings):profiles_preserved=False;continue
        for old,new in zip(old_rings,new_rings):
            if not np.allclose(old['center'],new['center'],rtol=0,atol=1e-8) or abs(old['radius_mm']-new['radius_mm'])>1e-8 or abs(old['z']-new['z'])>1e-8:
                profiles_preserved=False
    check('recognized_profile_rings_preserved',profiles_preserved,'Coaxial stepped/conical/rounded profiles retain every recognized ring center, radius and Z level; original wall and annular-shoulder vertices are protected exactly.')
    check('preservation_scope',True,'Protects recognized straight or complete coaxial Z-through profiles and vertex band only; not generic interfaces, CAD history, residual stress, fatigue or strength. STL circle fits and intersection predicates have numerical tolerances.')
    if not all(c['passed'] for c in checks):raise ValueError('Protected widening failed geometric checks; original retained: '+','.join(c['name'] for c in checks if not c['passed']))
    return candidate,checks,features
