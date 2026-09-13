"""Independent protected-edit contract, written before candidate integration.

Public development fixture: 60x30x4 plate, two diameter-6 Z through holes
at (-12,0) and (12,0). Resizing X to 80 must preserve every original bore
vertex exactly, each fitted radius, and the 24 mm center separation.
These assertions do not use the feature recognizer or candidate checker.
"""
from pathlib import Path
import numpy as np
import pytest
import trimesh
from cadforge.workspace import PythonWorkspace

CENTERS = np.array([[-12., 0.], [12., 0.]])
RADIUS = 3.


@pytest.fixture
def plate_workspace(tmp_path):
    plate = trimesh.creation.box(extents=[60, 30, 4])
    cutters = []
    for x, y in CENTERS:
        bore = trimesh.creation.cylinder(radius=RADIUS, height=10, sections=48)
        bore.apply_translation([x, y, 0])
        cutters.append(bore)
    plate = trimesh.boolean.difference([plate, *cutters], engine='manifold')
    source = tmp_path / 'two_hole_plate.stl'
    plate.export(source)
    workspace = PythonWorkspace(tmp_path / 'workspace', region_learning_path=tmp_path / 'learning.json')
    state = workspace.import_file(source)
    original = trimesh.load(state['parts'][0]['stl_path'], force='mesh')
    return workspace, state, original


def bore_vertices(mesh, center):
    radial = np.linalg.norm(mesh.vertices[:, :2] - center, axis=1)
    return mesh.vertices[np.abs(radial - RADIUS) < 2e-5]


def fit_circle(points):
    xy = np.unique(points[:, :2], axis=0)
    assert len(xy) >= 24, 'Too few independent bore samples'
    solution = np.linalg.lstsq(np.column_stack([2 * xy, np.ones(len(xy))]), (xy**2).sum(axis=1), rcond=None)[0]
    center = solution[:2]
    radius = np.sqrt(solution[2] + center @ center)
    residual = np.max(np.abs(np.linalg.norm(xy-center, axis=1)-radius))
    return center, radius, residual


def assert_preserved(original, candidate):
    candidate_coords = set(map(tuple, candidate.vertices))
    fitted = []
    for center in CENTERS:
        required = bore_vertices(original, center)
        assert len(required) >= 48, 'Fixture must contain actual bore-wall vertices'
        assert all(tuple(v) in candidate_coords for v in required), 'Original bore-wall vertex coordinates changed'
        actual = bore_vertices(candidate, center)
        fitted_center, radius, residual = fit_circle(actual)
        assert radius == pytest.approx(RADIUS, abs=2e-6)
        assert residual < 2e-6
        np.testing.assert_allclose(fitted_center, center, atol=2e-6)
        fitted.append(fitted_center)
    assert np.linalg.norm(fitted[1]-fitted[0]) == pytest.approx(24., abs=2e-6)


def test_ordinary_resize_is_valid_but_violates_hole_contract(plate_workspace):
    workspace, state, original = plate_workspace
    preview = workspace.preview(state['id'], {'op':'resize', 'axis':'x', 'target_mm':80}, {'part_id':state['parts'][0]['id']})
    assert preview['accepted']
    candidate = trimesh.load(preview['parts'][0]['stl_path'], force='mesh')
    assert candidate.is_watertight and candidate.volume > 0
    assert candidate.extents[0] == pytest.approx(80)
    with pytest.raises(AssertionError, match='Original bore-wall vertex coordinates changed'):
        assert_preserved(original, candidate)


def test_protected_resize_preserves_independent_contract_and_exports(plate_workspace):
    workspace, state, original = plate_workspace
    original_bytes = workspace.export_path(state['id']).read_bytes()
    preview = workspace.preview(state['id'], {'op':'resize_preserving_holes','axis':'x','target_mm':80}, {'part_id':state['parts'][0]['id']})
    assert preview['accepted'], repr(preview)
    candidate = trimesh.load(preview['parts'][0]['stl_path'], force='mesh')
    assert_preserved(original, candidate)
    assert candidate.extents[0] == pytest.approx(80, abs=2e-5)
    np.testing.assert_allclose(candidate.extents[1:], original.extents[1:], atol=2e-5)
    assert candidate.is_watertight and candidate.volume > 0
    assert workspace.export_path(state['id']).read_bytes() == original_bytes
    workspace.commit(state['id'], preview['preview_id'])
    exported = trimesh.load(workspace.export_path(state['id']), force='mesh')
    assert_preserved(original, exported)
    workspace.undo(state['id'])
    assert workspace.export_path(state['id']).read_bytes() == original_bytes


def test_impossible_protected_resize_rejected_without_state_change(plate_workspace):
    workspace, state, original = plate_workspace
    original_bytes = workspace.export_path(state['id']).read_bytes()
    preview = workspace.preview(state['id'], {'op':'resize_preserving_holes','axis':'x','target_mm':10}, {'part_id':state['parts'][0]['id']})
    assert not preview['accepted']
    assert any(not check['passed'] for check in preview['checks'])
    assert workspace.state(state['id']) == state
    assert workspace.export_path(state['id']).read_bytes() == original_bytes
    with pytest.raises(ValueError):
        workspace.commit(state['id'], preview['preview_id'])


def test_protection_request_without_identifiable_holes_fails_closed(tmp_path):
    source = tmp_path / 'solid_plate.stl'
    trimesh.creation.box(extents=[60, 30, 4]).export(source)
    workspace = PythonWorkspace(tmp_path / 'workspace')
    state = workspace.import_file(source)
    preview = workspace.preview(state['id'], {'op':'resize_preserving_holes','axis':'x','target_mm':80}, {'part_id':state['parts'][0]['id']})
    assert not preview['accepted'], 'A generic resize must not masquerade as verified hole protection'
    assert workspace.state(state['id']) == state


@pytest.mark.parametrize('scale', [0.01, 1., 1000.])
def test_normalized_intersection_policy_rejects_true_crossings(scale):
    from cadforge.protected_edit import _numerical_check_mesh
    from cadforge.region_edit import _intersecting_pairs
    # Two triangles intersect transversely, with no shared vertex indices.
    vertices = np.array([[-2,-2,0], [2,-2,0], [0,2,0], [0,-1,-1], [0,-1,1], [0,1,0]], dtype=float) * scale
    crossing = trimesh.Trimesh(vertices=vertices, faces=[[0,1,2], [3,4,5]], process=False)
    assert _intersecting_pairs(_numerical_check_mesh(crossing), np.array([0,1])) is not None
    separated = crossing.copy()
    separated.vertices[3:, 0] += 10 * scale
    assert _intersecting_pairs(_numerical_check_mesh(separated), np.array([0,1])) is None
