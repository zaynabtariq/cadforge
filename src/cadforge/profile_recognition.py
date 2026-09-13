"""Conservative recognition of vertical coaxial through-hole mesh profiles.

Recognizes rings, inward cylindrical/conical/rounded wall patches and explicit
annular shoulders. It does not reconstruct CAD history or guess blind/slanted
channels. All accepted profile vertices are returned for exact protection.
"""
from __future__ import annotations

import numpy as np
import trimesh
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components


def _components(mesh, faces):
    faces=np.asarray(faces,dtype=int)
    if not len(faces):return []
    mapping=np.full(len(mesh.faces),-1,dtype=int);mapping[faces]=np.arange(len(faces))
    adjacent=mesh.face_adjacency
    pairs=adjacent[np.all(mapping[adjacent]>=0,axis=1)]
    if len(pairs):
        a,b=mapping[pairs[:,0]],mapping[pairs[:,1]]
        graph=coo_matrix((np.ones(2*len(a)),(np.r_[a,b],np.r_[b,a])),shape=(len(faces),len(faces)))
    else:graph=coo_matrix((len(faces),len(faces)))
    count,labels=connected_components(graph,directed=False)
    return [faces[labels==i] for i in range(count)]


def _levels(points,tolerance):
    order=np.argsort(points[:,2]);groups=[]
    for index in order:
        if not groups or abs(points[index,2]-points[groups[-1][0],2])>tolerance:
            groups.append([int(index)])
        else:groups[-1].append(int(index))
    return groups


def _circle(xy):
    if len(xy)<6:raise ValueError('Too few vertices for a complete circular ring')
    origin=xy.mean(axis=0);relative=xy-origin
    matrix=np.column_stack((2*relative,np.ones(len(relative))))
    coefficients,_,rank,_=np.linalg.lstsq(matrix,np.einsum('ij,ij->i',relative,relative),rcond=None)
    if rank<3:raise ValueError('Degenerate ring')
    center=coefficients[:2]+origin
    radii=np.linalg.norm(xy-center,axis=1);radius=float(radii.mean())
    tolerance=max(1e-4,radius*.002)
    residual=float(np.max(np.abs(radii-radius)))
    if radius<=1e-6 or residual>tolerance:raise ValueError('Noncircular ring')
    angles=np.unique(np.round(np.arctan2(xy[:,1]-center[1],xy[:,0]-center[0]),9));angles.sort()
    gap=float(np.max(np.diff(np.r_[angles,angles[0]+2*np.pi])))
    if gap>np.pi/2:raise ValueError('Incomplete angular ring coverage')
    return center,radius,residual,gap


def _patch(mesh,faces,z_tolerance):
    indices=np.unique(mesh.faces[faces]);points=np.asarray(mesh.vertices)[indices]
    levels=_levels(points,z_tolerance)
    if len(levels)<2:return None
    rings=[]
    for level in levels:
        xy=points[level,:2]
        try:center,radius,residual,gap=_circle(xy)
        except ValueError:return None
        rings.append({'center':center,'radius_mm':radius,'z':float(points[level,2].mean()),
                      'fit_residual_mm':residual,'max_angular_gap_rad':gap})
    center=np.mean([r['center'] for r in rings],axis=0)
    tolerance=max(1e-4,max(r['radius_mm'] for r in rings)*.002)
    if any(np.linalg.norm(r['center']-center)>tolerance for r in rings):return None
    radial=mesh.triangles_center[faces,:2]-center
    normal=mesh.face_normals[faces,:2]
    denominator=np.linalg.norm(radial,axis=1)*np.linalg.norm(normal,axis=1)
    if np.any(denominator<1e-12):return None
    cosine=np.einsum('ij,ij->i',radial,normal)/denominator
    if not np.all(cosine<-.9):return None
    return {'center':center,'rings':rings,'faces':faces,'indices':indices,'tolerance':tolerance}


def _boundary_loops(mesh,faces,z_min,z_max,tolerance):
    edges=np.sort(np.asarray(mesh.faces)[faces][:,[[0,1],[1,2],[2,0]]].reshape(-1,2),axis=1)
    unique,counts=np.unique(edges,axis=0,return_counts=True)
    if np.any(counts>2):raise ValueError('Nonmanifold hole-profile surface')
    boundary=unique[counts==1]
    vertices,degree=np.unique(boundary,return_counts=True)
    if not len(boundary) or np.any(degree!=2):raise ValueError('Hole-profile boundary is not closed rings')
    graph={int(v):[] for v in vertices}
    for a,b in boundary:graph[int(a)].append(int(b));graph[int(b)].append(int(a))
    remaining=set(graph);loops=[]
    while remaining:
        pending=[remaining.pop()];component=[]
        while pending:
            vertex=pending.pop();component.append(vertex)
            for neighbor in graph[vertex]:
                if neighbor in remaining:remaining.remove(neighbor);pending.append(neighbor)
        loops.append(component)
    if len(loops)!=2:raise ValueError('Profile has missing shoulders, gaps, or extra openings')
    endpoints=[]
    for loop in loops:
        points=np.asarray(mesh.vertices)[loop]
        if np.ptp(points[:,2])>tolerance:raise ValueError('Slanted profile boundary')
        _circle(points[:,:2])
        endpoints.append(float(points[:,2].mean()))
    if not np.allclose(sorted(endpoints),[z_min,z_max],rtol=0,atol=tolerance):
        raise ValueError('Profile is blind or does not span the full Z thickness')


def recognize_coaxial_holes(mesh):
    """Return (feature dictionaries, unique original protected vertex indices)."""
    if (not isinstance(mesh,trimesh.Trimesh) or not mesh.is_watertight or
            not mesh.is_winding_consistent or mesh.volume<=0 or mesh.body_count!=1):
        raise ValueError('One closed, positively oriented connected mesh is required')
    if len(mesh.faces)>100000 or not np.isfinite(mesh.vertices).all():
        raise ValueError('Finite mesh with at most100000 triangles required')
    z_min,z_max=map(float,mesh.bounds[:,2]);z_tolerance=max(1e-5,(z_max-z_min)*1e-6)
    nonhorizontal=np.flatnonzero(np.abs(mesh.face_normals[:,2])<1-1e-6)
    patches=[p for faces in _components(mesh,nonhorizontal) if (p:=_patch(mesh,faces,z_tolerance)) is not None]
    if not patches:raise ValueError('No complete inward circular coaxial wall profiles recognized')
    groups=[]
    for patch in patches:
        matches=[g for g in groups if np.linalg.norm(g[0]['center']-patch['center'])<=min(g[0]['tolerance'],patch['tolerance'])]
        if len(matches)>1:raise ValueError('Ambiguous coaxial patch grouping')
        if matches:matches[0].append(patch)
        else:groups.append([patch])
    horizontal=np.flatnonzero(np.abs(mesh.face_normals[:,2])>=1-1e-6)
    triangles=np.asarray(mesh.triangles)
    features=[];protected=[]
    for group in groups:
        center=np.mean([p['center'] for p in group],axis=0)
        rings=[r for patch in group for r in patch['rings']]
        rings.sort(key=lambda r:(r['z'],r['radius_mm']))
        if abs(rings[0]['z']-z_min)>z_tolerance or abs(rings[-1]['z']-z_max)>z_tolerance:
            raise ValueError('Recognized inward profile is blind or incomplete across Z')
        # Full rings at differing radii on one Z level require an actual annular
        # shoulder. Protect its triangles too, then verify connected wall topology.
        shoulder_faces=[]
        for i,first in enumerate(rings):
            same=[r for r in rings[i+1:] if abs(r['z']-first['z'])<=z_tolerance]
            if not same:continue
            low=min([first['radius_mm']]+[r['radius_mm'] for r in same])
            high=max([first['radius_mm']]+[r['radius_mm'] for r in same])
            tolerance=max(1e-4,high*.002)
            if high-low<=tolerance:continue
            at_level=horizontal[np.all(np.abs(triangles[horizontal,:,2]-first['z'])<=z_tolerance,axis=1)]
            radial=np.linalg.norm(triangles[at_level,:,:2]-center,axis=2)
            inside=np.all((radial>=low-tolerance)&(radial<=high+tolerance),axis=1)
            shoulder_faces.extend(at_level[inside].tolist())
        faces=np.unique(np.r_[np.concatenate([p['faces'] for p in group]),shoulder_faces]).astype(int)
        if len(_components(mesh,faces))!=1:raise ValueError('Coaxial segments lack a continuous annular shoulder')
        _boundary_loops(mesh,faces,z_min,z_max,z_tolerance)
        indices=np.unique(mesh.faces[faces]);protected.extend(indices.tolist())
        serial_rings=[{k:(v.tolist() if isinstance(v,np.ndarray) else v) for k,v in r.items()} for r in rings]
        radii=[r['radius_mm'] for r in rings]
        features.append({'center':center.tolist(),'radius_mm':float(max(radii)),
                         'z_min':z_min,'z_max':z_max,'fit_residual_mm':float(max(r['fit_residual_mm'] for r in rings)),
                         'protected_vertex_count':len(indices),
                         'profile':{'kind':'coaxial_through_profile','rings':serial_rings,
                                    'minimum_radius_mm':float(min(radii)), 'maximum_radius_mm':float(max(radii)),
                                    'annular_shoulder_triangle_count':len(set(shoulder_faces)),
                                    'protected_face_count':len(faces)}})
    if mesh.euler_number!=2-2*len(features):
        raise ValueError('Recognized profile count does not explain mesh genus; ambiguous channels remain')
    return sorted(features,key=lambda f:tuple(f['center'])),np.unique(protected).astype(int)
