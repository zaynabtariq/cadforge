"""Bounded transfer to editable robot links with measured pivot invariants.

This is a geometric two-pivot link, not a qualified robot arm or universal CAD
editor. Widening preserves pivot locations/bores, length and thickness; it changes
mass/inertia and does not preserve load ratings without further analysis.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math
from pathlib import Path

import cadquery as cq
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box


@dataclass(frozen=True)
class RobotLinkSpec:
    center_distance: float = 80.0
    width: float = 20.0
    thickness: float = 6.0
    pivot_diameter: float = 4.0
    boss_outer_diameter: float = 12.0
    boss_height: float = 2.0
    end_extension: float = 12.0
    min_edge_distance: float = 2.0
    interface_max_width: float = 40.0

    def validate(self):
        if any(not math.isfinite(v) or not 0 < v <= 2000 for v in asdict(self).values()):
            raise ValueError("robot link parameters must be finite positive millimeters <=2000")
        if self.width > self.interface_max_width:
            raise ValueError("requested width exceeds fixed interface envelope")
        if self.boss_outer_diameter < self.pivot_diameter + 2 * self.min_edge_distance:
            raise ValueError("boss has insufficient radial bearing material")
        if self.width < self.boss_outer_diameter + 2 * self.min_edge_distance:
            raise ValueError("requested width violates boss edge-distance budget")
        if self.end_extension < self.boss_outer_diameter / 2 + self.min_edge_distance:
            raise ValueError("longitudinal edge distance is insufficient")
        if self.center_distance <= self.boss_outer_diameter:
            raise ValueError("pivot bosses overlap")


@dataclass(frozen=True)
class RobotLink:
    spec: RobotLinkSpec
    shape: cq.Shape
    version_id: str
    parent_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class BRepMeasurements:
    pivot_centers: tuple[tuple[float, float], ...]
    pivot_diameters: tuple[float, ...]
    pivot_axis_directions: tuple[tuple[float, float, float], ...]
    center_distance: float
    width: float
    length: float
    total_thickness: float
    valid_single_solid: bool
    volume_mm3: float
    boss_diameters: tuple[float, ...]


@dataclass(frozen=True)
class ChangeResult:
    accepted: bool
    active_link: RobotLink
    previous_version: str
    candidate_version: str | None
    checks: dict[str, bool]
    before: BRepMeasurements
    after: BRepMeasurements | None
    error: str | None = None
    learned_skill_ids: tuple[str, ...] = ()


def _version(spec, parents=()):
    data = {"spec": asdict(spec), "parent_ids": parents, "recipe": "two-pivot-link-v1",
            "cadquery": cq.__version__}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def build_link(spec: RobotLinkSpec, *, parent_ids=()) -> RobotLink:
    spec.validate()
    length = spec.center_distance + 2 * spec.end_extension
    shape = cq.Workplane("XY").box(length, spec.width, spec.thickness, centered=(True, True, False)).val()
    for x in (-spec.center_distance / 2, spec.center_distance / 2):
        boss = cq.Workplane("XY").circle(spec.boss_outer_diameter / 2).extrude(spec.boss_height).translate((x, 0, spec.thickness)).val()
        shape = shape.fuse(boss)
    for x in (-spec.center_distance / 2, spec.center_distance / 2):
        bore = cq.Workplane("XY").circle(spec.pivot_diameter / 2).extrude(spec.thickness + spec.boss_height + 2).translate((x, 0, -1)).val()
        shape = shape.cut(bore)
    if not shape.isValid() or len(shape.Solids()) != 1:
        raise ValueError("robot link construction did not produce one valid solid")
    return RobotLink(spec, shape, _version(spec, tuple(parent_ids)), tuple(parent_ids))


def measure_link(shape: cq.Shape) -> BRepMeasurements:
    """Measure internal cylindrical surfaces directly, independent of the spec.

    Selector is restricted to this two-through-bore recipe. Arbitrary imported
    shapes need their own feature identification and invariant contracts.
    """
    pivots, bosses = {}, {}
    for face in shape.Faces():
        if face.geomType() != "CYLINDER":
            continue
        surface = BRepAdaptor_Surface(face.wrapped)
        cylinder = surface.Cylinder()
        axis = cylinder.Axis()
        location, direction = axis.Location(), axis.Direction()
        vector = (direction.X(), direction.Y(), direction.Z())
        if abs(vector[2]) < 1 - 1e-8:
            raise ValueError("pivot axis is not normal to the link plane")
        center = (round(location.X(), 8), round(location.Y(), 8))
        diameter = 2 * cylinder.Radius()
        point = face.positionAt((surface.FirstUParameter() + surface.LastUParameter()) / 2,
                                (surface.FirstVParameter() + surface.LastVParameter()) / 2)
        normal = face.normalAt(point)
        radial_dot = (point.x - location.X()) * normal.x + (point.y - location.Y()) * normal.y
        if radial_dot > 0:
            bosses[center] = diameter
            continue
        if center in pivots and abs(pivots[center][0] - diameter) > 1e-7:
            raise ValueError("ambiguous stepped pivot bore")
        pivots[center] = (diameter, (0.0, 0.0, 1.0))
    if len(pivots) != 2:
        raise ValueError("expected exactly two independently measured pivot axes")
    if set(bosses) != set(pivots):
        raise ValueError("expected an independently measured outer boss at each pivot")
    centers = tuple(sorted(pivots))
    # STL export attaches triangulation to the BRep. Default bounding boxes can
    # then expand with mesh deflection. Measure analytic geometry exclusively.
    bounds = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.wrapped, bounds, False, False)
    xmin, ymin, zmin, xmax, ymax, zmax = bounds.Get()
    return BRepMeasurements(centers, tuple(pivots[p][0] for p in centers),
                            tuple(pivots[p][1] for p in centers), math.dist(*centers),
                            ymax - ymin, xmax - xmin, zmax - zmin,
                            shape.isValid() and len(shape.Solids()) == 1, shape.Volume(),
                            tuple(bosses[p] for p in centers))


def _invariants(before, after, new_width, spec):
    close = lambda a, b: abs(a - b) <= 1e-7
    return {
        "valid_single_solid": after.valid_single_solid,
        "pivot_axes_preserved": before.pivot_axis_directions == after.pivot_axis_directions,
        "pivot_centers_preserved": all(math.dist(a, b) <= 1e-7 for a, b in zip(before.pivot_centers, after.pivot_centers)),
        "pivot_distance_preserved": close(before.center_distance, after.center_distance),
        "pivot_diameters_preserved": all(close(a, b) for a, b in zip(before.pivot_diameters, after.pivot_diameters)),
        "boss_diameters_preserved": all(close(a, b) for a, b in zip(before.boss_diameters, after.boss_diameters)),
        "length_preserved": close(before.length, after.length),
        "thickness_preserved": close(before.total_thickness, after.total_thickness),
        "requested_width_measured": close(after.width, new_width),
        "interface_envelope": after.width <= spec.interface_max_width + 1e-7,
        "edge_distance_budget": after.width >= spec.boss_outer_diameter + 2 * spec.min_edge_distance - 1e-7,
    }


def widen_link(link: RobotLink, new_width: float, *, output_dir: str | Path | None = None) -> ChangeResult:
    """Versioned width change with measured invariants and automatic rollback."""
    before = measure_link(link.shape)
    candidate = None
    after = None
    checks = {}
    try:
        proposed_spec = replace(link.spec, width=float(new_width))
        proposed_spec.validate()
        if new_width <= link.spec.width:
            raise ValueError("widen_link requires an increased width")
        candidate = build_link(proposed_spec, parent_ids=(link.version_id,))
        after = measure_link(candidate.shape)
        checks = _invariants(before, after, new_width, proposed_spec)
        if not all(checks.values()):
            raise ValueError("measured invariant violation: " + ", ".join(k for k, v in checks.items() if not v))
        result = ChangeResult(True, candidate, link.version_id, candidate.version_id, checks, before, after)
    except Exception as error:
        result = ChangeResult(False, link, link.version_id, candidate.version_id if candidate else None,
                              checks or {"request_and_geometry_valid": False}, before, after,
                              f"{type(error).__name__}: {error}")
    if output_dir is not None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        payload = {"operation": "widen_preserving_pivots_v1", "requested_width": new_width if math.isfinite(new_width) else repr(new_width),
                   "accepted": result.accepted, "active_version": result.active_link.version_id,
                   "previous_version": result.previous_version, "candidate_version": result.candidate_version,
                   "checks": result.checks, "before": asdict(result.before),
                   "after": asdict(result.after) if result.after else None, "error": result.error}
        # Deterministic immutable operation record; an existing matching record is reused.
        encoded = json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n"
        audit_id = hashlib.sha256(encoded.encode()).hexdigest()
        record = out / f"change-{audit_id}.json"
        if record.exists():
            if record.read_text() != encoded:
                raise ValueError("immutable operation record mismatch")
        else:
            record.write_text(encoded)
        if result.accepted:
            export_link(result.active_link, out / result.active_link.version_id)
    return result


def export_link(link: RobotLink, directory: str | Path) -> dict[str, str]:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    paths = {kind: str((directory / f"robot_link.{extension}").resolve())
             for kind, extension in [("step", "step"), ("stl", "stl"), ("json", "json"), ("python", "py")]}
    cq.exporters.export(link.shape, paths["step"])
    cq.exporters.export(link.shape, paths["stl"])
    Path(paths["json"]).write_text(json.dumps({"spec": asdict(link.spec), "version_id": link.version_id,
                                             "parent_ids": link.parent_ids, "measurements": asdict(measure_link(link.shape))}, indent=2) + "\n")
    Path(paths["python"]).write_text(
        '"""Editable robot link; run with cadforge installed."""\n'
        'from pathlib import Path\nfrom cadforge.robotics import RobotLinkSpec, build_link, export_link\n'
        f'SPEC = {asdict(link.spec)!r}\n'
        'if __name__ == "__main__":\n    export_link(build_link(RobotLinkSpec(**SPEC)), Path(__file__).parent / "regenerated")\n')
    return paths


def apply_learned_fit(spec: RobotLinkSpec, service, context, *, hardware_diameter: float,
                      radial_clearance: float, min_wall: float) -> RobotLinkSpec:
    """Apply promoted local fit commands before fixing a robot link's pivot design.

    This initial sizing can change bore diameter; it is deliberately separate
    from widen_link, whose contract preserves the existing pivot geometry.
    Actual robot validation must follow; coupon success is not robot qualification.
    """
    parameters = service.apply("supported_fastener", {
        "fastener_diameter": hardware_diameter, "radial_clearance": radial_clearance,
        "min_wall": min_wall, "bore_diameter": spec.pivot_diameter,
        "boss_outer_diameter": spec.boss_outer_diameter,
    }, context=context)
    result = replace(spec, pivot_diameter=parameters["bore_diameter"],
                     boss_outer_diameter=parameters["boss_outer_diameter"], min_edge_distance=min_wall)
    result.validate()
    return result


def robot_fit_executor(template: RobotLinkSpec, output_dir: str | Path | None = None):
    """Real robot-link BRep callback for persistent transfer/monitor evidence."""
    from .continual import Measurement

    def execute(parameters, case_id):
        spec = replace(template, pivot_diameter=parameters["bore_diameter"],
                       boss_outer_diameter=parameters["boss_outer_diameter"],
                       min_edge_distance=parameters["min_wall"])
        link = build_link(spec)
        measured = measure_link(link.shape)
        overlaps, missing_walls = [], []
        for x, y in measured.pivot_centers:
            clearance_radius = parameters["fastener_diameter"] / 2 + parameters["radial_clearance"]
            probe = cq.Workplane("XY").circle(clearance_radius).extrude(spec.thickness + spec.boss_height + 2).translate((x, y, -1)).val()
            overlaps.append(link.shape.intersect(probe).Volume())
            hole_radius = measured.pivot_diameters[len(missing_walls)] / 2
            ring = cq.Workplane("XY").circle(hole_radius + parameters["min_wall"]).circle(hole_radius).extrude(spec.boss_height).translate((x, y, spec.thickness)).val()
            missing_walls.append(ring.cut(link.shape).Volume())
        checks = {
            "valid_robot_link": measured.valid_single_solid,
            "robot_pivot_clearance": max(overlaps) < 1e-6,
            "robot_bearing_wall": max(missing_walls) < 1e-6,
            "robot_pivot_distance": abs(measured.center_distance - template.center_distance) < 1e-7,
        }
        values = {"bore_diameter": min(measured.pivot_diameters),
                  "boss_outer_diameter": min(measured.boss_diameters),
                  "pivot_distance": measured.center_distance, "max_overlap_mm3": max(overlaps),
                  "max_missing_wall_mm3": max(missing_walls)}
        digests = {}
        if output_dir is not None:
            directory = Path(output_dir) / hashlib.sha256(case_id.encode()).hexdigest()[:16]
            paths = export_link(link, directory)
            report = directory / "fit_evidence.json"
            report.write_text(json.dumps({"case_id": case_id, "checks": checks, "measurements": values,
                                          "scope": "ideal robot-link BRep fit only"}, indent=2) + "\n")
            for path in [Path(p) for p in paths.values()] + [report]:
                digests[str(path.resolve())] = hashlib.sha256(path.read_bytes()).hexdigest()
        return Measurement(all(checks.values()), values, tuple(k for k, v in checks.items() if not v), checks, digests)
    return execute
