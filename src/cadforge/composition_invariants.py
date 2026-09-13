"""Conservative exact protected-hole surface contracts for mesh compositions."""
import hashlib
import json
import numpy as np
import trimesh
from .axial_protected_edit import recognize_axial_holes


def hole_signature(path):
    mesh=trimesh.load(path,force='mesh')
    _,_,features,indices=recognize_axial_holes(mesh)
    indices=np.asarray(indices,dtype=int)
    protected=np.zeros(len(mesh.vertices),dtype=bool);protected[indices]=True
    faces=mesh.faces[np.all(protected[mesh.faces],axis=1)]
    # Canonical cyclic ordering retains face orientation while removing storage
    # index/order differences introduced by STL import.
    triangles=sorted(min(tuple(np.roll(t,k,axis=0).flatten()) for k in range(3)) for t in mesh.vertices[faces])
    vertices=sorted(map(tuple,mesh.vertices[indices]))
    payload=json.dumps({'vertices':vertices,'triangles':triangles},allow_nan=False,separators=(',',':'))
    return {'sha256':hashlib.sha256(payload.encode()).hexdigest(),'recognized_holes':len(features),'protected_vertices':len(vertices),'protected_faces':len(faces)}


def capture(parts,invariants):
    if not isinstance(invariants,list) or len(invariants)>8:raise ValueError('At most eight invariant contracts supported')
    result=[]
    for contract in invariants:
        if not isinstance(contract,dict) or set(contract)!={'kind','part_id'} or contract['kind']!='preserve_holes':
            raise ValueError('Supported invariant: preserve_holes with explicit part_id')
        part=next((p for p in parts if p['id']==contract['part_id']),None)
        if part is None:raise ValueError('Invariant targets an unknown part')
        result.append({**contract,'baseline':hole_signature(part['stl_path'])})
    return result


def check(parts,contracts):
    checks=[]
    for contract in contracts:
        part=next((p for p in parts if p['id']==contract['part_id']),None)
        try:
            current=hole_signature(part['stl_path']) if part else None
            good=current==contract['baseline']
            detail='Original recognized hole vertices and oriented protected faces must remain exact after every step.'
        except ValueError as error:good=False;detail=str(error)
        checks.append({'name':'invariant.preserve_holes','passed':good,'detail':detail})
    return checks
