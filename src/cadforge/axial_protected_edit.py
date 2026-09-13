"""Compose checked hole widening with exact cyclic coordinate permutations.

Supports X-, Y- or Z-aligned complete through profiles. Oblique axes remain
unsupported; no interpolating rotation or relaxed recognition is used.
"""
import numpy as np
import trimesh
from .protected_edit import _recognized,resize_preserving_holes


def recognize_axial_holes(mesh):
    recognized=[]
    for order in ((0,1,2),(1,2,0),(2,0,1)):
        local=trimesh.Trimesh(vertices=np.asarray(mesh.vertices)[:,order],faces=mesh.faces.copy(),process=False)
        try:
            features,indices=_recognized(local)
        except ValueError:continue
        recognized.append((order,local,features,indices))
    if len(recognized)!=1:raise ValueError('Require one unambiguous coordinate-aligned through-hole direction')
    return recognized[0]


def resize_preserving_axial_holes(mesh,axis,target_mm,min_wall_mm=1):
    world_axis={'x':0,'y':1,'z':2}.get(axis)
    if world_axis is None:raise ValueError('Protected workspace widening requires x, y or z')
    order,local,_,indices=recognize_axial_holes(mesh)
    local_axis=order.index(world_axis)
    if local_axis==2:raise ValueError('Cannot widen along the protected bore direction')
    # Recognition chooses the frame before execution. A rejected widening is
    # never retried through another orientation or checker.
    changed,checks,features=resize_preserving_holes(local,local_axis,target_mm,min_wall_mm)
    vertices=np.asarray(changed.vertices)[:,np.argsort(order)]
    result=trimesh.Trimesh(vertices=vertices,faces=changed.faces.copy(),process=False)
    exact=np.array_equal(result.vertices[indices],mesh.vertices[indices])
    checks.append({'name':'world_hole_vertices_exact','passed':exact,'detail':'Original protected vertices keep their world coordinates exactly after a cyclic coordinate permutation.'})
    if not exact:raise ValueError('World-coordinate hole preservation failed')
    if order!=(0,1,2):
        for check in checks:
            if check['name']=='z_coordinates_exact':
                check['name']='bore_axis_coordinates_exact'
                check['detail']='Local Z is world '+ 'xyz'[order[2]]+'; thickness coordinates are unchanged.'
        for feature in features:feature['local_to_world_axes']=list(order)
    checks.append({'name':'coordinate_frame','passed':True,'detail':{'local_to_world_axes':list(order),'scope':'Exact coordinate permutation; inherited checks operate in that local frame.'}})
    return result,checks,features
