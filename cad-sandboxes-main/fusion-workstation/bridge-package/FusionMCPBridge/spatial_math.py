"""3D spatial math toolkit for Fusion 360 MCP Bridge.

Provides high-level geometry operations built on Fusion's native
Matrix3D / Vector3D / Point3D classes plus Python's math module.

Key functions:
  face_frame(face)              → (origin, normal, u_axis, v_axis)
  body_frame(body, face_hint)   → coordinate frame from a body face
  align_transform(src, tgt)     → Matrix3D to move src frame onto tgt frame
  placement_transform(...)      → Matrix3D from high-level placement spec
  apply_transform(occ, matrix)  → apply Matrix3D to an occurrence
"""

import math
import adsk.core
import adsk.fusion


# ── Point / Vector helpers ──────────────────────────────────

def pt(x, y, z):
    """Create a Point3D (in cm, Fusion internal units)."""
    return adsk.core.Point3D.create(x, y, z)


def vec(x, y, z):
    """Create a Vector3D."""
    return adsk.core.Vector3D.create(x, y, z)


def pt_mm(x, y, z):
    """Create a Point3D from mm coordinates."""
    return adsk.core.Point3D.create(x / 10.0, y / 10.0, z / 10.0)


def vec_from_pts(p1, p2):
    """Vector from p1 to p2."""
    return adsk.core.Vector3D.create(
        p2.x - p1.x, p2.y - p1.y, p2.z - p1.z)


def cross(a, b):
    """Cross product of two Vector3D."""
    return adsk.core.Vector3D.create(
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x)


def dot(a, b):
    """Dot product of two Vector3D."""
    return a.x * b.x + a.y * b.y + a.z * b.z


def length(v):
    """Length of a Vector3D."""
    return math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z)


def normalized(v):
    """Return a normalized copy of Vector3D."""
    mag = length(v)
    if mag < 1e-10:
        return adsk.core.Vector3D.create(0, 0, 1)
    return adsk.core.Vector3D.create(v.x / mag, v.y / mag, v.z / mag)


def negated(v):
    """Return negated copy of Vector3D."""
    return adsk.core.Vector3D.create(-v.x, -v.y, -v.z)


def scaled(v, s):
    """Return scaled copy of Vector3D."""
    return adsk.core.Vector3D.create(v.x * s, v.y * s, v.z * s)


def pt_add_vec(p, v):
    """Point3D + Vector3D → Point3D."""
    return adsk.core.Point3D.create(p.x + v.x, p.y + v.y, p.z + v.z)


def pt_to_mm(p):
    """Convert Point3D from cm to mm."""
    return [round(p.x * 10, 4), round(p.y * 10, 4), round(p.z * 10, 4)]


def vec_to_list(v):
    """Vector3D to [x, y, z] list."""
    return [round(v.x, 6), round(v.y, 6), round(v.z, 6)]


# ── Coordinate frame ────────────────────────────────────────

class Frame:
    """A right-handed coordinate frame: origin + X/Y/Z axes."""

    def __init__(self, origin, x_axis, y_axis, z_axis=None):
        self.origin = origin
        self.x_axis = normalized(x_axis)
        self.y_axis = normalized(y_axis)
        self.z_axis = normalized(z_axis) if z_axis else normalized(cross(x_axis, y_axis))

    def to_dict(self):
        return {
            "origin_mm": pt_to_mm(self.origin),
            "x_axis": vec_to_list(self.x_axis),
            "y_axis": vec_to_list(self.y_axis),
            "z_axis": vec_to_list(self.z_axis),
        }

    @staticmethod
    def world():
        """World coordinate frame at origin."""
        return Frame(pt(0, 0, 0), vec(1, 0, 0), vec(0, 1, 0), vec(0, 0, 1))

    @staticmethod
    def from_normal_and_point(origin, normal, up_hint=None):
        """Create a frame from a point and a normal (Z axis).
        Derives X and Y axes from the normal and an up hint.
        """
        z = normalized(normal)
        if up_hint is None:
            # Pick an up hint that's not parallel to the normal
            if abs(dot(z, vec(0, 0, 1))) < 0.9:
                up_hint = vec(0, 0, 1)
            else:
                up_hint = vec(0, 1, 0)
        x = normalized(cross(up_hint, z))
        y = normalized(cross(z, x))
        return Frame(origin, x, y, z)


# ── Face / Body geometry extraction ─────────────────────────

def face_frame(face):
    """Extract a coordinate frame from a BRepFace.

    Returns a Frame with:
      - origin at face centroid
      - Z axis = face normal (outward)
      - X axis = tangent along face (derived from evaluator)
      - Y axis = completes right-hand system
    """
    evaluator = face.evaluator
    # Get centroid via parameter space center
    param_range = evaluator.parametricRange()
    min_pt = param_range.minPoint
    max_pt = param_range.maxPoint
    mid_u = (min_pt.x + max_pt.x) / 2.0
    mid_v = (min_pt.y + max_pt.y) / 2.0
    mid_param = adsk.core.Point2D.create(mid_u, mid_v)

    (ok, origin) = evaluator.getPointAtParameter(mid_param)
    (ok, normal) = evaluator.getNormalAtParameter(mid_param)

    # Get tangent at the same point for X axis
    (ok, tangent_u, tangent_v) = evaluator.getFirstDerivative(mid_param)

    x_axis = normalized(tangent_u)
    z_axis = normalized(normal)
    y_axis = normalized(cross(z_axis, x_axis))

    return Frame(origin, x_axis, y_axis, z_axis)


def edge_direction(edge):
    """Get the direction vector of a linear edge."""
    evaluator = edge.evaluator
    (ok, start, end) = evaluator.getEndPoints()
    return normalized(vec_from_pts(start, end))


def body_bbox_frame(body, face_selector=None):
    """Get a coordinate frame from a body's bounding box.

    face_selector: "top", "bottom", "front", "back", "left", "right"
    Defaults to "bottom" (Z-min face, common for CNC).
    """
    bbox = body.boundingBox
    min_p = bbox.minPoint
    max_p = bbox.maxPoint
    center = pt(
        (min_p.x + max_p.x) / 2,
        (min_p.y + max_p.y) / 2,
        (min_p.z + max_p.z) / 2)

    selector = (face_selector or "bottom").lower()
    face_map = {
        "bottom": (pt(center.x, center.y, min_p.z), vec(0, 0, -1)),
        "top":    (pt(center.x, center.y, max_p.z), vec(0, 0, 1)),
        "front":  (pt(center.x, max_p.y, center.z), vec(0, 1, 0)),
        "back":   (pt(center.x, min_p.y, center.z), vec(0, -1, 0)),
        "left":   (pt(min_p.x, center.y, center.z), vec(-1, 0, 0)),
        "right":  (pt(max_p.x, center.y, center.z), vec(1, 0, 0)),
    }
    if selector not in face_map:
        raise Exception(f"Unknown face selector: {selector}. Use: {list(face_map.keys())}")

    origin, normal = face_map[selector]
    return Frame.from_normal_and_point(origin, normal)


# ── Transform computation ───────────────────────────────────

def align_transform(source_frame, target_frame):
    """Compute Matrix3D that moves source_frame to target_frame.

    Uses Fusion's built-in setToAlignCoordinateSystems which handles
    the full rotation + translation in one step.
    """
    matrix = adsk.core.Matrix3D.create()
    matrix.setToAlignCoordinateSystems(
        source_frame.origin,
        source_frame.x_axis,
        source_frame.y_axis,
        source_frame.z_axis,
        target_frame.origin,
        target_frame.x_axis,
        target_frame.y_axis,
        target_frame.z_axis,
    )
    return matrix


def placement_transform(
    panel_dims_mm,
    target_origin_mm,
    target_x_dir,
    target_y_dir,
    target_z_dir=None,
):
    """Compute transform to place a panel (modeled flat at origin) into
    an assembly at a specific position and orientation.

    Args:
        panel_dims_mm: [length, width, thickness] in mm (X, Y, Z of the flat part)
        target_origin_mm: [x, y, z] in mm — where the panel's min corner goes
        target_x_dir: [x, y, z] — direction the panel's X axis (length) maps to
        target_y_dir: [x, y, z] — direction the panel's Y axis (width) maps to
        target_z_dir: [x, y, z] — direction the panel's Z axis (thickness) maps to
                      (computed from cross product if omitted)

    Returns: Matrix3D
    """
    lx, ly, lz = panel_dims_mm
    tx, ty, tz = [v / 10.0 for v in target_origin_mm]

    # Source frame: panel center at origin
    src_origin = pt(0, 0, 0)
    src_x = vec(1, 0, 0)
    src_y = vec(0, 1, 0)
    src_z = vec(0, 0, 1)
    src = Frame(src_origin, src_x, src_y, src_z)

    # Target frame
    tgt_x = normalized(vec(*target_x_dir))
    tgt_y = normalized(vec(*target_y_dir))
    tgt_z = normalized(vec(*target_z_dir)) if target_z_dir else normalized(cross(tgt_x, tgt_y))
    tgt_origin = pt(tx, ty, tz)
    tgt = Frame(tgt_origin, tgt_x, tgt_y, tgt_z)

    return align_transform(src, tgt)


def matrix_to_dict(matrix):
    """Dump a Matrix3D as a readable dict for debugging."""
    data = []
    for row in range(4):
        r = []
        for col in range(4):
            r.append(round(matrix.getCell(row, col), 6))
        data.append(r)
    t = matrix.translation
    return {
        "rows": data,
        "translation_cm": [round(t.x, 6), round(t.y, 6), round(t.z, 6)],
        "translation_mm": [round(t.x * 10, 2), round(t.y * 10, 2), round(t.z * 10, 2)],
        "is_identity": all(
            abs(matrix.getCell(r, c) - (1.0 if r == c else 0.0)) < 1e-6
            for r in range(4) for c in range(4)),
    }


def apply_transform_to_occurrence(occurrence, matrix):
    """Apply a Matrix3D transform to an occurrence."""
    occurrence.transform = matrix


# ── High-level placement helpers ────────────────────────────

def make_side_panel_transform(
    panel_height_mm, panel_depth_mm, panel_thickness_mm,
    side, carcass_width_mm, carcass_height_mm,
):
    """Compute transform for a side panel in a carcass assembly.

    The part is modeled flat: X=height, Y=depth, Z=thickness, centered at origin.

    Args:
        side: "left" or "right" (cabinet convention: left=+X, right=-X when
              looking from front)
        carcass_width_mm: total outer width
        carcass_height_mm: total outer height

    Returns: Matrix3D
    """
    half_w = carcass_width_mm / 2.0 / 10.0  # to cm
    half_h = panel_height_mm / 2.0 / 10.0
    half_d = panel_depth_mm / 2.0 / 10.0
    t = panel_thickness_mm / 10.0

    # Source: actual center of the part (centered in XY, Z from 0 to t)
    src = Frame(pt(0, 0, t / 2), vec(1, 0, 0), vec(0, 1, 0), vec(0, 0, 1))

    if side == "left":
        # Left panel (positive X in cabinet convention)
        # Panel X (height) → assembly +Z (up)
        # Panel Y (depth) → assembly +Y (front-back)
        # Z = X cross Y = (0,0,1) cross (0,1,0) = (-1,0,0)
        # That means outer face points -X, but we want it at +X.
        # So flip: Panel X → -Z, Panel Y → +Y, computed Z → +X
        tgt_origin = pt(half_w - t / 2, 0, half_h)
        tgt_x = vec(0, 0, -1)  # panel height goes downward in Z (flipped)
        tgt_y = vec(0, 1, 0)   # depth stays +Y
        # Z = X cross Y = (0,0,-1) cross (0,1,0) = (1,0,0) ✓ outer at +X
        tgt = Frame(tgt_origin, tgt_x, tgt_y)
    elif side == "right":
        # Right panel (negative X)
        # Panel X (height) → assembly +Z (up)
        # Panel Y (depth) → assembly +Y
        # Z = X cross Y = (0,0,1) cross (0,1,0) = (-1,0,0) ✓ outer at -X
        tgt_origin = pt(-half_w + t / 2, 0, half_h)
        tgt_x = vec(0, 0, 1)
        tgt_y = vec(0, 1, 0)
        tgt = Frame(tgt_origin, tgt_x, tgt_y)
    else:
        raise Exception(f"Unknown side: {side}. Use 'left' or 'right'.")

    return align_transform(src, tgt)


def make_top_bottom_panel_transform(
    panel_length_mm, panel_depth_mm, panel_thickness_mm,
    position, carcass_height_mm,
):
    """Compute transform for a top or bottom panel.

    The part is modeled flat: X=length, Y=depth, Z=thickness, centered at origin.

    Args:
        position: "top" or "bottom"
        carcass_height_mm: total outer height

    Returns: Matrix3D
    """
    h = carcass_height_mm / 10.0  # to cm
    t = panel_thickness_mm / 10.0

    # Source: actual center of the part (centered in XY, Z from 0 to t)
    src = Frame(pt(0, 0, t / 2), vec(1, 0, 0), vec(0, 1, 0), vec(0, 0, 1))

    if position == "top":
        # Top panel: Z thickness at the top of the carcass
        # Outer face (Z=thickness in part) maps to top of carcass
        tgt_origin = pt(0, 0, h - t / 2)
        tgt = Frame(tgt_origin, vec(1, 0, 0), vec(0, 1, 0), vec(0, 0, 1))
    elif position == "bottom":
        tgt_origin = pt(0, 0, t / 2)
        tgt = Frame(tgt_origin, vec(1, 0, 0), vec(0, 1, 0), vec(0, 0, 1))
    else:
        raise Exception(f"Unknown position: {position}. Use 'top' or 'bottom'.")

    return align_transform(src, tgt)
