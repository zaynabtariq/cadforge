from dataclasses import replace
import json
import pytest
import cadquery as cq

import cadforge.robotics as robotics
from cadforge.robotics import RobotLinkSpec, build_link, measure_link, widen_link, robot_fit_executor


def test_widen_robot_link_preserves_measured_lever_geometry(tmp_path):
    original = build_link(RobotLinkSpec())
    before = measure_link(original.shape)
    assert before.pivot_centers == ((-40., 0.), (40., 0.))
    assert before.pivot_diameters == pytest.approx((4., 4.))
    assert before.boss_diameters == pytest.approx((12., 12.))
    changed = widen_link(original, 28., output_dir=tmp_path)
    assert changed.accepted
    assert all(changed.checks.values())
    assert changed.active_link.parent_ids == (original.version_id,)
    assert changed.active_link.version_id != original.version_id
    assert changed.after.pivot_centers == before.pivot_centers
    assert changed.after.width == pytest.approx(28.)
    assert changed.after.volume_mm3 > before.volume_mm3
    # Verify the exported BRep, not only the in-memory construction.
    exported = tmp_path / changed.active_link.version_id / "robot_link.step"
    imported = cq.importers.importStep(str(exported)).val()
    assert measure_link(imported).pivot_diameters == pytest.approx((4., 4.))
    records = list(tmp_path.glob("change-*.json"))
    assert len(records) == 1 and json.loads(records[0].read_text())["accepted"]


@pytest.mark.parametrize("width,reason", [(45., "interface"), (10., "edge-distance"), (float("nan"), "finite")])
def test_invalid_width_rolls_back_without_mutating_geometry(width, reason, tmp_path):
    original = build_link(RobotLinkSpec())
    previous_volume = original.shape.Volume()
    changed = widen_link(original, width, output_dir=tmp_path)
    assert not changed.accepted
    assert changed.active_link is original
    assert reason in changed.error
    assert original.shape.Volume() == previous_volume
    assert not list(tmp_path.glob("*/robot_link.step"))


def test_checker_catches_geometry_drift_even_when_metadata_claims_correct(monkeypatch):
    original = build_link(RobotLinkSpec())
    real_builder = robotics.build_link
    def broken_builder(spec, **kwargs):
        built = real_builder(spec, **kwargs)
        # Simulate a CAD edit accidentally translating the full link by 1 mm.
        return replace(built, shape=built.shape.translate((1., 0., 0.)))
    monkeypatch.setattr(robotics, "build_link", broken_builder)
    changed = widen_link(original, 28.)
    assert not changed.accepted
    assert not changed.checks["pivot_centers_preserved"]
    assert changed.active_link is original


def test_robot_brep_fit_callback_reports_executed_positive_and_negative_evidence():
    execute = robot_fit_executor(RobotLinkSpec())
    parameters = {"bore_diameter": 4.4, "boss_outer_diameter": 8.4,
                  "fastener_diameter": 4., "radial_clearance": .2, "min_wall": 2.}
    positive = execute(parameters, "robot-positive")
    assert positive.passed
    assert positive.measurements["max_overlap_mm3"] == pytest.approx(0)
    negative = execute(parameters | {"bore_diameter": 4.}, "robot-negative")
    assert not negative.passed
    assert "robot_pivot_clearance" in negative.failure_codes
    assert negative.measurements["max_overlap_mm3"] > 0


def test_initial_learned_fit_is_separate_from_widening():
    class RecordedService:
        def apply(self, name, parameters, **kwargs):
            assert name == "supported_fastener"
            return parameters | {"bore_diameter": 3.4, "boss_outer_diameter": 6.4}
    fitted = robotics.apply_learned_fit(RobotLinkSpec(), RecordedService(), object(),
                                       hardware_diameter=3., radial_clearance=.2, min_wall=1.5)
    link = build_link(fitted)
    changed = widen_link(link, 28.)
    assert changed.accepted
    assert changed.after.pivot_diameters == pytest.approx((3.4, 3.4))


def test_stl_export_cannot_change_analytic_invariant_measurements(tmp_path):
    spec = RobotLinkSpec(pivot_diameter=2.799999999999999,
                         boss_outer_diameter=5.8000000000000025, min_edge_distance=1.5)
    original = build_link(spec)
    before = measure_link(original.shape)
    robotics.export_link(original, tmp_path / "before")
    # Tessellation is now attached; invariants still use exact BRep geometry.
    after_export = measure_link(original.shape)
    assert abs(before.total_thickness - after_export.total_thickness) <= 1e-7
    assert abs(before.length - after_export.length) <= 1e-7
    assert abs(before.width - after_export.width) <= 1e-7
    changed = widen_link(original, 30., output_dir=tmp_path / "after")
    assert changed.accepted, changed.error
    assert all(changed.checks.values())
