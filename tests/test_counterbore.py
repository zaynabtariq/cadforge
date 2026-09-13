"""Independent polygon, depth and protected-bore contracts for counterbores."""
import math
import numpy as np
import pytest
import trimesh
from cadforge.counterbore import counterbore,CounterboreError


def stock(sections=48):
    return trimesh.boolean.difference([trimesh.creation.box(extents=[30,30,10]),trimesh.creation.cylinder(radius=2,height=12,sections=sections)],engine='manifold')


@pytest.mark.parametrize('direction',[-1,1])
@pytest.mark.parametrize('sections',[32,48,64])
def test_real_counterbore_preserves_lower_bore_and_annular_floor(direction,sections):
    original=stock(sections);before_vertices=original.vertices.copy();before_faces=original.faces.copy()
    result,checks,feature=counterbore(original,4,3,[0,0,-direction*5],direction)
    assert all(check['passed'] for check in checks)
    assert np.array_equal(original.vertices,before_vertices) and np.array_equal(original.faces,before_faces)
    assert result.is_watertight and result.euler_number==0
    expected=(32*16*math.sin(2*math.pi/64)-sections/2*4*math.sin(2*math.pi/sections))*3
    assert original.volume-result.volume==pytest.approx(expected,rel=5e-6)
    floor=-direction*2
    floor_faces=np.all(np.abs(result.triangles[:,:,2]-floor)<1e-6,axis=1)
    assert floor_faces.any()
    assert result.area_faces[floor_faces].sum()==pytest.approx(expected/3,rel=5e-6)
    # Mid-thickness original bore boundary is unchanged below the recess.
    original_section=original.section(plane_normal=[0,0,1],plane_origin=[0,0,0])
    final_section=result.section(plane_normal=[0,0,1],plane_origin=[0,0,0])
    assert original_section.length==pytest.approx(final_section.length,abs=1e-6)
    lower=original.vertices[(np.linalg.norm(original.vertices[:,:2],axis=1)<2.01)&(original.vertices[:,2]*direction>2)]
    assert all(any(np.array_equal(v,w) for w in result.vertices) for v in lower)
    assert feature['original_bore_radius_mm']==pytest.approx(2,abs=1e-6)
    assert feature['protected_void_repair']['initial_intersection_faces']>=0


@pytest.mark.parametrize('radius,depth,entry,direction',[
    (1,3,[0,0,5],-1),(2,3,[0,0,5],-1),
    (4,10,[0,0,5],-1),(4,11,[0,0,5],-1),
    (4,3,[.1,0,5],-1),(4,3,[0,0,4],-1),
    (16,3,[0,0,5],-1),(4,3,[0,0,5],1),
    (4,3,[0,0,5],0),(float('nan'),3,[0,0,5],-1),
])
def test_invalid_request_rejects_without_mutation(radius,depth,entry,direction):
    original=stock();vertices=original.vertices.copy();faces=original.faces.copy()
    with pytest.raises(ValueError):counterbore(original,radius,depth,entry,direction)
    assert np.array_equal(original.vertices,vertices) and np.array_equal(original.faces,faces)


def test_second_void_inside_annular_floor_fails_closed():
    original=stock();extra=trimesh.creation.cylinder(radius=.05,height=12,sections=32);extra.apply_translation([3,0,0])
    original=trimesh.boolean.difference([original,extra],engine='manifold')
    with pytest.raises(CounterboreError):counterbore(original,4,3,[0,0,5])


def test_non_z_and_already_stepped_bores_are_unsupported():
    original=stock();original.apply_transform(trimesh.transformations.rotation_matrix(.4,[1,0,0]))
    with pytest.raises(CounterboreError):counterbore(original,4,3,[0,0,original.bounds[1,2]])
    stepped,_,_=counterbore(stock(),4,3,[0,0,5])
    with pytest.raises(CounterboreError):counterbore(stepped,5,2,[0,0,5])


def test_known_protected_void_reapplication_records_actual_failure_and_repair():
    result,checks,feature=counterbore(stock(48),4,3,[0,0,5])
    record=feature['protected_void_repair']
    assert record['applied'] and record['initial_intersection_faces']>0
    # The discovered issue is zero-volume coincident faces, not measured bulk
    # obstruction. The repair still must satisfy the unchanged empty-face gate.
    assert abs(record['initial_intersection_volume_mm3'])<1e-10
    assert next(c['passed'] for c in checks if c['name']=='counterbore.original_bore_open')


def test_browser_fitted_center_roundoff_keeps_exact_coverage_guards(tmp_path):
    # Actual browser failure: least-squares center is ~1e-16 away from zero;
    # learned diameter arithmetic also yields 3.499999999999999 radius.
    path=tmp_path/'browser.stl';stock(48).export(path)
    original=trimesh.load(path,force='mesh',process=True)
    entry=[5.123798353954577e-17,-1.237952507359822e-16,5]
    result,checks,feature=counterbore(original,3.499999999999999,2,entry)
    assert all(c['passed'] for c in checks)
    assert feature['requested_entry']==entry
    assert 0<feature['center_roundoff_mm']<=feature['center_roundoff_budget_mm']<1e-12
    assert feature['entry']==[0,0,5]
    coverage=next(c for c in checks if c['name']=='counterbore.annular_stock_coverage')
    assert coverage['detail']['missing_stock_faces']==0
    assert next(c['passed'] for c in checks if c['name']=='counterbore.original_bore_open')
    assert result.euler_number==original.euler_number
