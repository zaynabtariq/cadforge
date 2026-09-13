import hashlib
import json
from types import SimpleNamespace
import cadquery as cq
import trimesh
from cadforge.schema import DesignSpec
from cadforge.handoff import write_handoff
from cadforge.handoff_geometry import screen_handoff_geometry


def package(tmp_path):
    source=tmp_path/'design.py';source.write_text('raise RuntimeError("Never execute packaged source")')
    result=SimpleNamespace(spec=DesignSpec(family='glasses'),parts={'plate':cq.Workplane('XY').box(12,20,3).val()})
    return write_handoff(result,{'python':source},tmp_path)


def rehash(manifest,relative):
    from pathlib import Path
    path=Path(manifest);data=json.loads(path.read_text());body=(path.parent/relative).read_bytes()
    data['files'][relative]={'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()}
    path.write_text(json.dumps(data))


def test_real_export_passes_without_executing_source(tmp_path):
    r=screen_handoff_geometry(package(tmp_path))
    assert r['geometry_passed'] and r['production_ready'] is False
    assert r['parts'][0]['measurements']['step_volume_mm3']==720


def test_hash_consistent_open_mesh_fails_geometry(tmp_path):
    p=package(tmp_path);file=tmp_path/'parts/plate.stl'
    mesh=trimesh.load(file,force='mesh');mesh.update_faces(range(len(mesh.faces)-1));mesh.export(file)
    rehash(p,'parts/plate.stl');r=screen_handoff_geometry(p)
    assert r['integrity']['integrity_passed'] and not r['geometry_passed']
    assert not next(c for c in r['parts'][0]['checks'] if c['name']=='mesh_closed_positive_winding')['passed']


def test_hash_consistent_wrong_solid_fails_dimensions(tmp_path):
    p=package(tmp_path);trimesh.creation.box(extents=[12,20,6]).export(tmp_path/'parts/plate.stl')
    rehash(p,'parts/plate.stl');r=screen_handoff_geometry(p)
    assert r['integrity']['integrity_passed'] and not r['geometry_passed']
    assert not next(c for c in r['parts'][0]['checks'] if c['name']=='mesh_step_volume')['passed']


def test_exact_bounds_do_not_depend_on_export_triangulation(tmp_path):
    import numpy as np
    from cadforge.handoff import exact_bounds
    shape=cq.Workplane('XY').circle(7.3).extrude(2).val().rotate((0,0,0),(0,1,0),17)
    def measured():
        b=exact_bounds(shape)
        return [b.xmin,b.ymin,b.zmin,b.xmax,b.ymax,b.zmax]
    before=measured()
    cq.exporters.export(shape,str(tmp_path/'coarse.stl'),tolerance=0.5,angularTolerance=0.5)
    assert np.allclose(before,measured(),rtol=0,atol=1e-10)


def test_shifted_hole_with_matching_bounds_and_volume_is_rejected(tmp_path):
    def plate(x):return cq.Workplane('XY').box(20,20,6).val().cut(cq.Solid.makeCylinder(2,8,cq.Vector(x,0,-4)))
    source=tmp_path/'design.py';source.write_text('# inert')
    result=SimpleNamespace(spec=DesignSpec(family='glasses'),parts={'plate':plate(-3)})
    path=write_handoff(result,{'python':source},tmp_path)
    cq.exporters.export(plate(3),str(tmp_path/'parts/plate.stl'));rehash(path,'parts/plate.stl')
    report=screen_handoff_geometry(path);part=report['parts'][0]
    assert report['integrity']['integrity_passed'] and not report['geometry_passed']
    checks={c['name']:c['passed'] for c in part['checks']}
    assert checks['mesh_step_volume'] and checks['mesh_step_bounds']
    assert not checks['mesh_points_on_step_boundary']
    assert part['measurements']['maximum_mesh_surface_distance_mm']>1.9
