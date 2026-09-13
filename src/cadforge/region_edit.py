"""Bounded mesh-region deformation with immutable outside vertices and rollback.

This preserves triangle indices, not a source CAD feature tree. Intersection
checks use floating-point triangle SAT, not an exact geometric proof.
"""
import numpy as np
import trimesh
from scipy.spatial import cKDTree


class RegionEditError(ValueError):
    def __init__(self,message,trials=None):
        super().__init__(message);self.trials=trials or []


def _intersecting_pairs(mesh, changed_faces, max_pairs=200000):
    """Numerical triangle SAT with shrunken interiors to exclude shared boundaries."""
    triangles=np.asarray(mesh.triangles)
    centers=triangles.mean(axis=1)
    radii=np.linalg.norm(triangles-centers[:,None,:],axis=2).max(axis=1)
    tree=cKDTree(centers);lo=triangles.min(axis=1);hi=triangles.max(axis=1)
    selected=set(map(int,changed_faces));pairs=[]
    for i in changed_faces:
        candidates=np.asarray(tree.query_ball_point(centers[i],radii[i]+radii.max()+1e-9),dtype=int)
        candidates=candidates[candidates!=i]
        candidates=candidates[np.all(hi[candidates]>=lo[i]-1e-9,axis=1)&np.all(lo[candidates]<=hi[i]+1e-9,axis=1)]
        for j in candidates:
            if j in selected and j<i:continue
            pairs.append((int(i),int(j)))
            if len(pairs)>max_pairs:raise RegionEditError('Intersection-check pair budget exceeded; use a smaller mesh/selection')
    for start in range(0,len(pairs),1024):
        batch=np.asarray(pairs[start:start+1024]);a=triangles[batch[:,0]];b=triangles[batch[:,1]]
        # Exclude legal edge/vertex contact. Penetrations below this relative
        # numerical margin remain outside the claimed detection resolution.
        a=a.mean(axis=1)[:,None,:]+(a-a.mean(axis=1)[:,None,:])*(1-1e-8)
        b=b.mean(axis=1)[:,None,:]+(b-b.mean(axis=1)[:,None,:])*(1-1e-8)
        ea=np.roll(a,-1,axis=1)-a;eb=np.roll(b,-1,axis=1)-b
        na=np.cross(ea[:,0],ea[:,1]);nb=np.cross(eb[:,0],eb[:,1])
        axes=np.concatenate([na[:,None,:],nb[:,None,:],np.cross(ea[:,:,None,:],eb[:,None,:,:]).reshape(-1,9,3),np.cross(na[:,None,:],ea),np.cross(nb[:,None,:],eb)],axis=1)
        norm=np.linalg.norm(axes,axis=2);valid=norm>1e-12
        axes=axes/np.maximum(norm[:,:,None],1e-30)
        pa=np.einsum('nvc,nac->nav',a,axes);pb=np.einsum('nvc,nac->nav',b,axes)
        separated=((pa.max(axis=2)<pb.min(axis=2)-1e-10)|(pb.max(axis=2)<pa.min(axis=2)-1e-10))&valid
        hit=np.flatnonzero(~separated.any(axis=1))
        if len(hit):return tuple(map(int,batch[hit[0]]))
    return None


def _validate(original,candidate,mask):
    checks=[]
    def add(name,passed,detail):checks.append({'name':name,'passed':bool(passed),'detail':detail})
    add('outside_vertices_exact',np.array_equal(original.vertices[~mask],candidate.vertices[~mask]),'All vertices outside selected AABB remain bitwise unchanged.')
    add('triangle_indices_preserved',np.array_equal(original.faces,candidate.faces),'Original triangle indices and vertex count retained.')
    add('finite_vertices',np.isfinite(candidate.vertices).all(),'No NaN/infinite coordinates.')
    add('watertight_positive_volume',candidate.is_watertight and candidate.is_winding_consistent and candidate.volume>1e-10,'Closed consistently oriented mesh with positive signed volume.')
    cross=np.cross(candidate.triangles[:,1]-candidate.triangles[:,0],candidate.triangles[:,2]-candidate.triangles[:,0])
    original_cross=np.cross(original.triangles[:,1]-original.triangles[:,0],original.triangles[:,2]-original.triangles[:,0])
    add('no_collapsed_faces',np.all(np.linalg.norm(cross,axis=1)>1e-10),'All triangle doubled areas exceed numerical floor.')
    add('no_flipped_faces',np.all(np.einsum('ij,ij->i',cross,original_cross)>0),'Every normal retains positive dot product with its original normal; conservative under large rotations.')
    if all(c['passed'] for c in checks):
        changed=np.flatnonzero(np.any(mask[original.faces],axis=1))
        hit=_intersecting_pairs(candidate,changed)
        add('no_detected_triangle_intersection',hit is None,'Floating-point interior triangle SAT, relative boundary margin1e-8; '+('no intersection detected' if hit is None else f'intersecting faces {hit}'))
    return checks


def deform_region(mesh,command,region):
    if not isinstance(mesh,trimesh.Trimesh):raise RegionEditError('Expected a triangular mesh')
    if len(mesh.faces)>100000:raise RegionEditError('Region editing is limited to100000 triangles for bounded validation')
    lo=np.asarray(region['min'],dtype=float);hi=np.asarray(region['max'],dtype=float)
    if lo.shape!=(3,) or hi.shape!=(3,) or not np.isfinite([lo,hi]).all() or np.any(hi<=lo):raise RegionEditError('Selection bounds must be finite with positive extent')
    if not mesh.is_watertight or not mesh.is_winding_consistent or mesh.volume<=0:raise RegionEditError('Input must be a positive watertight consistently wound mesh')
    if _intersecting_pairs(mesh,np.arange(len(mesh.faces))) is not None:
        raise RegionEditError('Input already has detected intersecting triangle interiors')
    vertices=np.asarray(mesh.vertices).copy();mask=np.all((vertices>=lo)&(vertices<=hi),axis=1)
    if not mask.any():raise RegionEditError('Selection contains no mesh vertices; enlarge it or refine the mesh')
    axis=command.get('axis','x');axis={'x':0,'y':1,'z':2}.get(axis,axis)
    if axis not in (0,1,2):raise RegionEditError('Axis must be x, y or z')
    op=command.get('op',command.get('type',command.get('action','')))
    delta=np.zeros_like(vertices)
    if op in ('translate','move'):
        amount=float(command.get('amount_mm',command.get('amount',0)))
        if not np.isfinite(amount) or abs(amount)<1e-12:raise RegionEditError('Nonzero finite translation amount_mm required')
        delta[mask,axis]=amount
    elif op in ('resize','scale'):
        target=float(command['target_mm']);current=np.ptp(vertices[mask,axis])
        if not np.isfinite(target) or target<=0 or current<=1e-10:raise RegionEditError('Positive target and nonzero selected vertex extent required')
        center=(lo[axis]+hi[axis])/2
        delta[mask,axis]=(vertices[mask,axis]-center)*(target/current-1)
    else:raise RegionEditError('Supported selected-region operations are translate and resize')
    mode=command.get('translation_mode','allow_transition')
    if mode not in ('allow_transition','rigid'):raise RegionEditError('translation_mode must be rigid or allow_transition')
    trials=[]
    strategies=[('sharp',np.ones(len(vertices)))]
    if op in ('translate','move') and mode!='rigid' and not mask.all():
        interior=np.maximum(0,np.min(np.minimum(vertices-lo,hi-vertices)/(hi-lo),axis=1))
        if interior[mask].max()>1e-12:
            for exponent in (1,2):
                weight=np.clip(interior/interior[mask].max(),0,1)**exponent
                strategies.append((f'interior_transition_power_{exponent}',weight))
    preferred=command.get('learned_strategy')
    if preferred:
        strategies.sort(key=lambda item: item[0]!=preferred)
    for strategy,weight in strategies:
        from .execution_budget import charge,BudgetExceeded
        try:charge('cad_candidates')
        except BudgetExceeded as exc:
            exc.trials=trials.copy()
            raise
        proposed=vertices+delta*weight[:,None]
        candidate=trimesh.Trimesh(vertices=proposed,faces=mesh.faces.copy(),process=False)
        try:checks=_validate(mesh,candidate,mask)
        except RegionEditError as exc:
            checks=[{'name':'bounded_intersection_validation','passed':False,'detail':str(exc)}]
        if op in ('translate','move'):
            achieved=np.max(np.abs(proposed[mask,axis]-vertices[mask,axis]))
            checks.append({'name':'requested_peak_translation','passed':bool(np.isclose(achieved,abs(amount),rtol=1e-9,atol=1e-9)),'detail':f'Requested interior peak {amount} mm; measured magnitude {achieved} mm. Transition strategy may move other selected vertices less.'})
            if mode=='rigid':
                actual=proposed[mask]-vertices[mask]
                checks.append({'name':'requested_rigid_translation','passed':bool(np.allclose(actual,delta[mask],rtol=1e-9,atol=1e-9)),'detail':'Every selected vertex must receive the complete requested displacement vector.'})
        elif op in ('resize','scale'):
            achieved=float(np.ptp(proposed[mask,axis]))
            checks.append({'name':'requested_selected_extent','passed':bool(np.isclose(achieved,target,rtol=1e-9,atol=1e-9)),'detail':f'Requested selected-vertex extent {target} mm; measured {achieved} mm. Resize never uses a transition that changes this target.'})
        trials.append({'strategy':strategy,'accepted':all(c['passed'] for c in checks),'checks':checks.copy()})
        if trials[-1]['accepted']:
            checks.append({'name':'repair_trials','passed':True,'detail':trials.copy()})
            checks.append({'name':'scope_limit','passed':True,'detail':'Preserves outside vertices and indices, not CAD history, wall thickness, design intent, exact predicates or mechanical validity.'})
            return candidate,checks
    raise RegionEditError('Requested edit failed geometric checks; original retained',trials)


def record_validated_transfer(path,mesh,command,region):
    """Promote a repair priority only after real correction on two distinct meshes.

    This stores executable strategy selection and measured provenance, not model
    fine-tuning. Every later use still executes all geometry checks.
    """
    from pathlib import Path
    import hashlib,json
    destination=Path(path);destination.parent.mkdir(parents=True,exist_ok=True)
    state=json.loads(destination.read_text()) if destination.exists() else {'version':1,'evidence':[],'skills':[]}
    proposed,checks=deform_region(mesh,command,region)
    trials=next(c['detail'] for c in checks if c['name']=='repair_trials')
    accepted=next(t for t in trials if t['accepted'])
    fingerprint=hashlib.sha256(mesh.vertices.tobytes()+mesh.faces.tobytes()).hexdigest()
    corrected=any(not t['accepted'] for t in trials) and accepted['strategy']!='sharp'
    record={'mesh_sha256':fingerprint,'command':command,'region':region,'trials':trials,'actual_correction':corrected}
    state['evidence'].append(record)
    if corrected:
        strategy=accepted['strategy']
        support={e['mesh_sha256'] for e in state['evidence'] if e['actual_correction'] and any(t['accepted'] and t['strategy']==strategy for t in e['trials'])}
        if len(support)>=2:
            state['skills']=[{'id':'region-interior-translation-v1','operation':'translate','strategy':strategy,
                'supporting_mesh_sha256':sorted(support),'validated_mesh_count':len(support),
                'execution':'Pass learned_strategy as preferred ordering to deform_region; full validation and rollback remain mandatory.',
                'limits':'Distinct mesh hashes are provenance, not a proof of broad design generalization.'}]
    temporary=destination.with_suffix(destination.suffix+'.tmp');temporary.write_text(json.dumps(state,indent=2)+'\n');temporary.replace(destination)
    return proposed,checks,state
