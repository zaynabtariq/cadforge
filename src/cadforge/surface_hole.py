"""Inherited planar-support-face drilling via an audited rigid local frame.

The corrected blind-hole operation remains the sole cutting/stock-coverage
backend. Nonplanar, recessed and non-support faces are intentionally rejected.
"""
import hashlib
import numpy as np
from scipy.spatial import cKDTree
import trimesh
from .blind_hole import drill_blind_hole,BlindHoleError


class SurfaceHoleError(ValueError):
    def __init__(self,message,checks=None):
        super().__init__(message);self.checks=checks or []


def drill_surface_hole(mesh,radius_mm,depth_mm,entry,normal):
    entry=np.asarray(entry,dtype=float);normal=np.asarray(normal,dtype=float)
    if entry.shape!=(3,) or normal.shape!=(3,) or not np.isfinite(entry).all() or not np.isfinite(normal).all():
        raise SurfaceHoleError('Finite3D entry and outward unit normal are required')
    length=float(np.linalg.norm(normal))
    if length<1e-12 or abs(length-1)>1e-6:raise SurfaceHoleError('Outward normal must be nonzero and unit length within1e-6')
    normal=normal/length
    reference=np.eye(3)[np.argmin(np.abs(normal))]
    u=np.cross(reference,normal);u/=np.linalg.norm(u);v=np.cross(normal,u)
    basis=np.column_stack((u,v,normal))
    local=mesh.copy();local.vertices=(np.asarray(mesh.vertices)-entry)@basis
    span=float(np.ptp(local.vertices[:,2]));tolerance=max(1e-6,span*1e-7)
    zmax=float(local.bounds[1,2]);checks=[]
    def check(name,passed,detail):checks.append({'name':name,'passed':bool(passed),'detail':detail})
    check('surface.entry_support_plane',abs(zmax)<=tolerance,f'Entry maps tolocalZ0; exterior support plane localZmax={zmax:.12g}mm, tolerance={tolerance:.12g}mm.')
    triangles=np.asarray(local.triangles)
    planar=np.all(np.abs(triangles[:,:,2])<=tolerance,axis=1)&(local.face_normals[:,2]>.999999)
    contained=False
    for triangle in triangles[planar,:,:2]:
        edges=np.roll(triangle,-1,axis=0)-triangle
        signs=edges[:,0]*(-triangle[:,1])-edges[:,1]*(-triangle[:,0])
        area_tolerance=tolerance*max(1,float(np.linalg.norm(edges,axis=1).max()))
        if np.all(signs>=-area_tolerance) or np.all(signs<=area_tolerance):contained=True;break
    check('surface.entry_on_planar_face',contained,'Entry must be inside an actual outward planar support-face triangle; tangent vertices, recessed faces and invented points are unsupported.')
    check('surface.rigid_frame',np.allclose(basis.T@basis,np.eye(3),rtol=0,atol=1e-12) and abs(np.linalg.det(basis)-1)<1e-12,'Orthonormal right-handed local frame; local+Z is supplied outward normal.')
    if not all(c['passed'] for c in checks):raise SurfaceHoleError('Selected entry/normal is not a supported planar exterior face',checks)
    # Serialized STL support faces can warp by bounded float32 coordinate error.
    # Repair only vertices belonging to verified outward support triangles;
    # retain every face, edge, and opening, and expose the displacement budget.
    support_indices=np.unique(local.faces[planar])
    displacement=float(np.max(np.abs(local.vertices[support_indices,2])))
    original_volume=float(local.volume)
    vertices=np.array(local.vertices,copy=True);vertices[support_indices,2]=0.0
    local.vertices=vertices
    check('surface.explicit_support_plane_repair',displacement<=tolerance and local.is_watertight and local.is_winding_consistent and local.volume>0,
        {'max_vertex_displacement_mm':displacement,'allowed_mm':tolerance,'vertices':len(support_indices),'volume_delta_mm3':float(local.volume-original_volume),
         'policy':'Project verified near-coplanar outward support-face vertices to requested entry plane; preserve all topology and openings. Inherited coverage checks run on this explicitly repaired input.'})
    if not checks[-1]['passed']:raise SurfaceHoleError('Bounded support plane repair failed',checks)
    # Manifold accepts float32 vertices. Make that representation boundary
    # explicit before measuring input volume, rather than charging whole-stock
    # re-quantization to the material removed by the drill.
    kernel_vertices=np.asarray(local.vertices,dtype=np.float32).astype(np.float64)
    kernel_displacement=float(np.linalg.norm(kernel_vertices-local.vertices,axis=1).max())
    local.vertices=kernel_vertices
    check('surface.kernel_input_representation',kernel_displacement<=tolerance and len(np.unique(kernel_vertices,axis=0))==len(kernel_vertices) and np.all(local.area_faces>0) and local.is_watertight and local.is_winding_consistent and local.volume>0,
          {'max_vertex_displacement_mm':kernel_displacement,'allowed_mm':tolerance,'policy':'Explicit float32 Boolean-kernel input representation; reject merged vertices or collapsed faces. Original-world removed-volume gate remains mandatory.'})
    if not checks[-1]['passed']:raise SurfaceHoleError('Kernel representation exceeds bounded displacement',checks)
    try:
        cut,inherited,feature=drill_blind_hole(local,radius_mm,depth_mm,[0,0,0],-1)
    except BlindHoleError as error:
        raise SurfaceHoleError(str(error),checks+error.checks) from error
    checks.extend(inherited)
    world=cut.copy();world.vertices=np.asarray(cut.vertices)@basis.T+entry
    # Restore surviving original vertices after the float32 Boolean round trip.
    # Only a unique source match within the declared representation budget is
    # restored; newly introduced bore vertices have no such match.
    original_vertices=np.asarray(mesh.vertices)
    distances,neighbors=cKDTree(original_vertices).query(world.vertices,k=2)
    nearest=neighbors[:,0]
    restore=(distances[:,0]<=tolerance)&(distances[:,1]>tolerance)
    world_vertices=np.array(world.vertices,copy=True)
    world_vertices[restore]=original_vertices[nearest[restore]]
    world.vertices=world_vertices
    expected=32*float(radius_mm)**2*np.sin(2*np.pi/64)*float(depth_mm)
    removed=float(mesh.volume-world.volume)
    check('surface.original_stock_removed_volume',abs(removed-expected)<=max(1e-5,expected*5e-6),
          {'removed_mm3':removed,'expected_mm3':expected,'restored_source_vertices':int(restore.sum())})
    check('surface.world_result_valid' ,world.is_watertight and world.is_winding_consistent and world.volume>0 and np.isfinite(world.vertices).all(),'Rigidly transformed output remains finite, positively oriented and watertight.')

    resolved=np.asarray(feature['entry'])@basis.T+entry
    bottom=np.array([0,0,feature['bottom_z']])@basis.T+entry
    transform=np.eye(4);transform[:3,:3]=basis;transform[:3,3]=entry
    inverse=np.eye(4);inverse[:3,:3]=basis.T;inverse[:3,3]=-basis.T@entry
    output={'kind':'surface_blind_hole','entry':entry.tolist(),'resolved_entry':resolved.tolist(),'normal':normal.tolist(),
        'radius_mm':float(radius_mm),'depth_mm':float(depth_mm),'bottom':bottom.tolist(),'facets':64,
        'local_to_world':transform.tolist(),'world_to_local':inverse.tolist(),'inherited_operation':'drill_blind_hole',
        'entry_plane_roundoff_mm':float(feature['entry'][2]),'support_plane_repair_mm':displacement,'kernel_representation_displacement_mm':kernel_displacement,'precision_normalization_mm':displacement+kernel_displacement,'support_plane_repair_vertices':len(support_indices),
        'source_geometry_sha256':hashlib.sha256(np.asarray(mesh.vertices).tobytes()+np.asarray(mesh.faces).tobytes()).hexdigest(),
        'restored_original_vertices':int(restore.sum()),
        'support_plane_residual_mm':displacement,'repair_policy':'Project verified planar support vertices locally; restore surviving unique original vertices after Boolean roundtrip. Topology and openings are preserved.',
        'scope':'Planar global support faces only. Five inherited blind-hole guards validate explicitly repaired local input and local cut. After original-vertex restoration, final world checks cover original-stock removed volume, finiteness, winding and watertightness; floor topology and stock coverage are not independently rerun in world coordinates. Inherited tolerances are unchanged.'}
    if not all(c['passed'] for c in checks):raise SurfaceHoleError('World-space surface drilling validation failed',checks)
    return world,checks,output
