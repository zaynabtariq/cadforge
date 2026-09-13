"""Reopen named fabrication exports and screen geometry independently of hashes.

These are bounded numerical consistency screens, not manufacturing approval or
proof that tessellated and exact shapes coincide at every surface point.
"""
import json
from pathlib import Path
import numpy as np
import cadquery as cq
import trimesh
from .handoff import verify_handoff, exact_bounds

# Fixed export-screen policy; callers cannot loosen it per failing package.
POLICY={'step_volume_relative':1e-7,'step_bounds_mm':0.001,
        'mesh_volume_relative':0.001,'mesh_bounds_mm':0.1,
        'mesh_surface_distance_mm':0.1,'maximum_surface_points':50000}


def mesh_surface_distance(exact,mesh):
    points=np.vstack((mesh.vertices,mesh.triangles_center))
    if len(points)>POLICY['maximum_surface_points']:
        raise ValueError('Export surface screen exceeds the fixed point budget')
    # A solid may give zero distance to an interior point. Measure shells so
    # a misplaced hole wall inside material cannot be mistaken for a match.
    boundary=cq.Compound.makeCompound(exact.Shells())
    maximum=max(cq.Vertex.makeVertex(*map(float,point)).distance(boundary) for point in points)
    if not np.isfinite(maximum):raise ValueError('Nonfinite surface distance')
    return float(maximum),len(points)


def screen_handoff_geometry(manifest_path):
    path=Path(manifest_path).resolve()
    integrity=verify_handoff(path)
    report={'integrity':integrity,'geometry_passed':False,'parts':[],
            'policy':dict(POLICY),'production_ready':False,
            'scope':'Named part validity, closure, solid/component counts, bounds, volume and mesh vertex/triangle-center distance to STEP shells. Sampling is not continuous surface equivalence or physical qualification.'}
    if not integrity['integrity_passed']:return report
    manifest=json.loads(path.read_text())
    for part in manifest['parts']:
        outcome={'name':part['name'],'checks':[],'measurements':{}}
        def check(name,passed):outcome['checks'].append({'name':name,'passed':bool(passed)})
        try:
            exact=cq.importers.importStep(str(path.parent/part['exports']['step'])).val()
            mesh=trimesh.load(path.parent/part['exports']['stl'],force='mesh',process=True)
            bbox=exact_bounds(exact)
            bounds=np.array([[bbox.xmin,bbox.ymin,bbox.zmin],[bbox.xmax,bbox.ymax,bbox.zmax]])
            volume=float(exact.Volume());mesh_volume=float(mesh.volume)
            finite=np.isfinite(bounds).all() and np.isfinite(mesh.vertices).all() and np.isfinite([volume,mesh_volume]).all()
            check('finite_geometry',finite)
            if not finite:raise ValueError('Nonfinite measured geometry')
            check('step_valid_positive_solids',exact.isValid() and volume>0 and all(s.isValid() and s.Volume()>0 for s in exact.Solids()))
            check('step_solid_count',len(exact.Solids())==part['solid_count'])
            check('mesh_closed_positive_winding',mesh.is_watertight and mesh.is_winding_consistent and mesh_volume>0)
            components=mesh.split(only_watertight=False)
            check('mesh_component_count',len(components)==part['solid_count'])
            check('mesh_components_positive_closed',all(m.is_watertight and m.is_winding_consistent and m.volume>0 for m in components))
            step_delta=abs(volume-part['volume_mm3'])/part['volume_mm3']
            mesh_delta=abs(mesh_volume-volume)/max(abs(volume),1e-30)
            step_bounds=float(np.max(np.abs(bounds-np.asarray(part['bounds_mm']))))
            mesh_bounds=float(np.max(np.abs(mesh.bounds-bounds)))
            outcome['measurements']={'step_volume_mm3':volume,'mesh_volume_mm3':mesh_volume,
                'step_volume_relative_error':step_delta,'mesh_volume_relative_error':mesh_delta,
                'step_bounds_error_mm':step_bounds,'mesh_bounds_error_mm':mesh_bounds,
                'step_solid_count':len(exact.Solids()),'mesh_component_count':len(components)}
            check('step_manifest_volume',step_delta<=POLICY['step_volume_relative'])
            check('step_manifest_bounds',step_bounds<=POLICY['step_bounds_mm'])
            check('mesh_step_volume',mesh_delta<=POLICY['mesh_volume_relative'])
            check('mesh_step_bounds',mesh_bounds<=POLICY['mesh_bounds_mm'])
            if all(c['passed'] for c in outcome['checks']):
                distance,points=mesh_surface_distance(exact,mesh)
                outcome['measurements'].update({'maximum_mesh_surface_distance_mm':distance,'surface_points_checked':points})
                check('mesh_points_on_step_boundary',distance<=POLICY['mesh_surface_distance_mm'])
        except Exception as error:
            check('geometry_read_and_measure',False)
            outcome['error']=f'{type(error).__name__}: {error}'
        outcome['passed']=bool(outcome['checks']) and all(c['passed'] for c in outcome['checks'])
        report['parts'].append(outcome)
    report['geometry_passed']=bool(report['parts']) and all(p['passed'] for p in report['parts'])
    return report
