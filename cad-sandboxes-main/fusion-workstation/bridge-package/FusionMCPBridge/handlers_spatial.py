"""Spatial reasoning handlers for Fusion 360 MCP Bridge.

READ-ONLY spatial queries that help the AI understand 3D geometry
and plan transforms before applying them.  Also includes joint-based
placement handlers that bypass manual rotation math.

Every public function has the signature ``handle_*(body: dict) -> dict``
and is registered in SPATIAL_ROUTES.

Endpoints (7):
  SPATIAL QUERIES (read-only)
    /spatial_face_map            – semantic face map of a body
    /spatial_transform_preview   – preview where faces end up after a transform
    /spatial_find_transform      – compute rotation+translation to place a face
    /spatial_find_placement      – find rotation satisfying multiple face constraints
  JOINT-BASED PLACEMENT (modifies model)
    /spatial_joint_placement     – place occurrence via Fusion joint system
    /spatial_joint_to_point      – place occurrence face at a target point+normal
"""

import math
import traceback

import adsk.core
import adsk.fusion

try:
    from bridge_helpers import (
        get_design, get_root, get_component_by_name, find_component, find_body,
        _all_component_names, _all_body_names,
        select_face, resolve_face_selector,
    )
except ImportError:
    from .bridge_helpers import (
        get_design, get_root, get_component_by_name, find_component, find_body,
        _all_component_names, _all_body_names,
        select_face, resolve_face_selector,
    )

try:
    from spatial_math import (
        pt, vec, pt_mm, pt_to_mm, vec_to_list, vec_from_pts,
        cross, dot, length, normalized, negated, scaled, pt_add_vec,
        Frame, face_frame, align_transform, matrix_to_dict,
        apply_transform_to_occurrence,
    )
except ImportError:
    from .spatial_math import (
        pt, vec, pt_mm, pt_to_mm, vec_to_list, vec_from_pts,
        cross, dot, length, normalized, negated, scaled, pt_add_vec,
        Frame, face_frame, align_transform, matrix_to_dict,
        apply_transform_to_occurrence,
    )


# ── Internal helpers ─────────────────────────────────────────

_AXIS_LABELS = {
    (1, 0, 0): "+X",   (-1, 0, 0): "-X",
    (0, 1, 0): "+Y",   (0, -1, 0): "-Y",
    (0, 0, 1): "+Z",   (0, 0, -1): "-Z",
}

_SEMANTIC_LABELS = {
    "+X": "right",  "-X": "left",
    "+Y": "front",  "-Y": "back",
    "+Z": "top",    "-Z": "bottom",
}


def _snap_normal(n):
    """Classify a normal vector to its nearest axis or 'angled'."""
    threshold = 0.95
    for axis_tuple, label in _AXIS_LABELS.items():
        ax = vec(*axis_tuple)
        if dot(n, ax) > threshold:
            return label
    return "angled"


def _semantic_label(axis_label, face_geom_type, angle_info=None):
    """Derive a semantic label from the axis classification."""
    if axis_label in _SEMANTIC_LABELS:
        return _SEMANTIC_LABELS[axis_label]
    return "miter"


def _face_bbox(face):
    """Get bounding box of a face in mm."""
    bb = face.boundingBox
    return {
        "min": pt_to_mm(bb.minPoint),
        "max": pt_to_mm(bb.maxPoint),
    }


def _face_area_mm2(face):
    """Get face area in mm^2 (Fusion stores in cm^2)."""
    return round(face.area * 100.0, 4)


def _face_centroid(face):
    """Get face centroid as Point3D."""
    evaluator = face.evaluator
    param_range = evaluator.parametricRange()
    min_pt = param_range.minPoint
    max_pt = param_range.maxPoint
    mid_u = (min_pt.x + max_pt.x) / 2.0
    mid_v = (min_pt.y + max_pt.y) / 2.0
    mid_param = adsk.core.Point2D.create(mid_u, mid_v)
    (ok, origin) = evaluator.getPointAtParameter(mid_param)
    return origin


def _face_normal(face):
    """Get face normal as Vector3D."""
    evaluator = face.evaluator
    param_range = evaluator.parametricRange()
    min_pt = param_range.minPoint
    max_pt = param_range.maxPoint
    mid_u = (min_pt.x + max_pt.x) / 2.0
    mid_v = (min_pt.y + max_pt.y) / 2.0
    mid_param = adsk.core.Point2D.create(mid_u, mid_v)
    (ok, normal) = evaluator.getNormalAtParameter(mid_param)
    return normalized(normal)


def _angle_to_planes(normal):
    """Compute angle (degrees) from the normal to each world plane."""
    world_normals = {
        "XY": vec(0, 0, 1),
        "XZ": vec(0, 1, 0),
        "YZ": vec(1, 0, 0),
    }
    angles = {}
    for name, wn in world_normals.items():
        cos_a = dot(normal, wn)
        cos_a = max(-1.0, min(1.0, cos_a))
        angles[name] = round(math.degrees(math.acos(abs(cos_a))), 2)
    return angles


def _classify_face(face, index, body_name):
    """Build the full face info dict for one BRepFace."""
    centroid = _face_centroid(face)
    normal = _face_normal(face)
    axis_label = _snap_normal(normal)

    geom = face.geometry
    if hasattr(geom, "surfaceType"):
        st = geom.surfaceType
        type_map = {0: "plane", 1: "cylinder", 2: "cone", 3: "sphere", 4: "torus", 5: "nurbs"}
        face_type = type_map.get(st, f"unknown_{st}")
    else:
        face_type = "plane" if isinstance(geom, adsk.core.Plane) else "other"

    info = {
        "face_id": f"{body_name}_face_{index}",
        "index": index,
        "type": face_type,
        "normal": vec_to_list(normal),
        "normal_direction": axis_label,
        "centroid_mm": pt_to_mm(centroid),
        "area_mm2": _face_area_mm2(face),
        "bounding_box": _face_bbox(face),
        "label": _semantic_label(axis_label, face_type),
    }

    if axis_label == "angled":
        info["angles_to_planes"] = _angle_to_planes(normal)

    return info


def _find_body_by_name(body_name, component_name=None):
    """Find a body by name, optionally within a specific component."""
    root = get_root()
    if component_name:
        comp, _ = get_component_by_name(component_name)
        if not comp:
            available = _all_component_names(root)
            raise Exception(
                f"Component '{component_name}' not found. Available: {available}")
        for b in comp.bRepBodies:
            if b.name == body_name:
                return b
        available = [b.name for b in comp.bRepBodies]
        raise Exception(
            f"Body '{body_name}' not found in component '{component_name}'. "
            f"Available: {available}")
    else:
        return find_body(body_name)


def _apply_rotation_to_vec(axis, angle_rad, v):
    """Apply Rodrigues' rotation formula to a vector.
    axis must be normalized.  angle in radians.
    """
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    k = axis
    # v_rot = v*cos(a) + (k x v)*sin(a) + k*(k.v)*(1-cos(a))
    kxv = cross(k, v)
    kdv = dot(k, v)
    return vec(
        v.x * cos_a + kxv.x * sin_a + k.x * kdv * (1 - cos_a),
        v.y * cos_a + kxv.y * sin_a + k.y * kdv * (1 - cos_a),
        v.z * cos_a + kxv.z * sin_a + k.z * kdv * (1 - cos_a),
    )


def _apply_rotation_to_pt(axis, angle_rad, origin, p):
    """Rotate a point around an axis through origin."""
    # Translate to origin, rotate, translate back
    v = vec(p.x - origin.x, p.y - origin.y, p.z - origin.z)
    vr = _apply_rotation_to_vec(axis, angle_rad, v)
    return pt(origin.x + vr.x, origin.y + vr.y, origin.z + vr.z)


def _rotation_between_vectors(src, tgt):
    """Compute axis and angle to rotate vector src onto vector tgt.

    Returns (axis: Vector3D, angle_rad: float, det: int).
    det is +1 for proper rotation, -1 if a reflection is needed.
    """
    src_n = normalized(src)
    tgt_n = normalized(tgt)

    d = dot(src_n, tgt_n)
    d = max(-1.0, min(1.0, d))

    if d > 0.9999:
        # Already aligned
        return vec(0, 0, 1), 0.0, 1

    if d < -0.9999:
        # 180 degrees — pick a perpendicular axis
        if abs(src_n.x) < 0.9:
            perp = normalized(cross(src_n, vec(1, 0, 0)))
        else:
            perp = normalized(cross(src_n, vec(0, 1, 0)))
        return perp, math.pi, 1

    axis = normalized(cross(src_n, tgt_n))
    angle = math.acos(d)
    return axis, angle, 1


def _matrix3x3_det(r00, r01, r02, r10, r11, r12, r20, r21, r22):
    """Compute determinant of a 3x3 matrix."""
    return (r00 * (r11 * r22 - r12 * r21)
            - r01 * (r10 * r22 - r12 * r20)
            + r02 * (r10 * r21 - r11 * r20))


def _check_rotation_matrix_det(matrix):
    """Check the 3x3 rotation part of a Matrix3D for proper rotation.
    Returns the determinant (should be +1 for proper rotation).
    """
    r = [[matrix.getCell(row, col) for col in range(3)] for row in range(3)]
    det = _matrix3x3_det(
        r[0][0], r[0][1], r[0][2],
        r[1][0], r[1][1], r[1][2],
        r[2][0], r[2][1], r[2][2])
    return round(det, 6)


# ── Face Map Handler ─────────────────────────────────────────

def handle_spatial_face_map(body):
    """For a body, classify all faces with semantic labels.

    Params:
        body_name    (required) – name of the body
        component    (optional) – component to search in
    """
    try:
        body_name = body.get("body_name")
        component_name = body.get("component")
        if not body_name:
            raise Exception("body_name is required")

        target_body = _find_body_by_name(body_name, component_name)

        faces = []
        for i in range(target_body.faces.count):
            f = target_body.faces.item(i)
            faces.append(_classify_face(f, i, body_name))

        # Group by direction for summary
        direction_summary = {}
        for f in faces:
            d = f["normal_direction"]
            if d not in direction_summary:
                direction_summary[d] = []
            direction_summary[d].append(f["face_id"])

        bbox = target_body.boundingBox
        return {
            "body": body_name,
            "component": component_name,
            "face_count": len(faces),
            "faces": faces,
            "direction_summary": direction_summary,
            "body_bounding_box_mm": {
                "min": pt_to_mm(bbox.minPoint),
                "max": pt_to_mm(bbox.maxPoint),
            },
        }
    except Exception as e:
        return {"error": True, "message": str(e), "traceback": traceback.format_exc()}


# ── Transform Preview Handler ────────────────────────────────

def handle_spatial_transform_preview(body):
    """Preview where each face of a body would end up after a transform.

    Params:
        body_name      (required) – name of the body
        component      (optional) – component to search in
        rotate_axis    (optional) – [x,y,z] rotation axis
        rotate_angle   (optional) – rotation angle in degrees
        rotate_origin  (optional) – [x,y,z] rotation center in mm (default [0,0,0])
        translate      (optional) – [x,y,z] translation in mm
    """
    try:
        body_name = body.get("body_name")
        component_name = body.get("component")
        if not body_name:
            raise Exception("body_name is required")

        target_body = _find_body_by_name(body_name, component_name)

        # Parse transform parameters
        rot_axis_raw = body.get("rotate_axis")
        rot_angle_deg = body.get("rotate_angle", 0)
        rot_origin_raw = body.get("rotate_origin", [0, 0, 0])
        translate_raw = body.get("translate", [0, 0, 0])

        has_rotation = rot_axis_raw is not None and rot_angle_deg != 0
        has_translation = any(v != 0 for v in translate_raw)

        rot_axis = normalized(vec(*rot_axis_raw)) if rot_axis_raw else vec(0, 0, 1)
        rot_angle = math.radians(rot_angle_deg)
        rot_origin = pt(rot_origin_raw[0] / 10.0, rot_origin_raw[1] / 10.0,
                        rot_origin_raw[2] / 10.0)
        translate = vec(translate_raw[0] / 10.0, translate_raw[1] / 10.0,
                        translate_raw[2] / 10.0)

        # Classify faces before and after
        faces_before = []
        faces_after = []
        for i in range(target_body.faces.count):
            f = target_body.faces.item(i)
            before = _classify_face(f, i, body_name)
            faces_before.append(before)

            # Compute new centroid and normal
            centroid = _face_centroid(f)
            normal = _face_normal(f)

            new_centroid = centroid
            new_normal = normal

            if has_rotation:
                new_centroid = _apply_rotation_to_pt(
                    rot_axis, rot_angle, rot_origin, new_centroid)
                new_normal = _apply_rotation_to_vec(
                    rot_axis, rot_angle, new_normal)

            if has_translation:
                new_centroid = pt(
                    new_centroid.x + translate.x,
                    new_centroid.y + translate.y,
                    new_centroid.z + translate.z)

            new_normal_n = normalized(new_normal)
            new_axis_label = _snap_normal(new_normal_n)

            faces_after.append({
                "face_id": before["face_id"],
                "index": i,
                "original_label": before["label"],
                "original_direction": before["normal_direction"],
                "new_centroid_mm": pt_to_mm(new_centroid),
                "new_normal": vec_to_list(new_normal_n),
                "new_direction": new_axis_label,
                "new_label": _semantic_label(new_axis_label, before["type"]),
            })

        return {
            "body": body_name,
            "transform": {
                "rotate_axis": vec_to_list(rot_axis) if has_rotation else None,
                "rotate_angle_deg": rot_angle_deg if has_rotation else None,
                "rotate_origin_mm": [round(v, 2) for v in rot_origin_raw] if has_rotation else None,
                "translate_mm": translate_raw if has_translation else None,
            },
            "faces_before": faces_before,
            "faces_after": faces_after,
            "face_count": len(faces_before),
        }
    except Exception as e:
        return {"error": True, "message": str(e), "traceback": traceback.format_exc()}


# ── Find Transform Handler ───────────────────────────────────

def handle_spatial_find_transform(body):
    """Compute rotation + translation to move a face to a target location.

    Params:
        body_name       (required) – name of the body
        component       (optional) – component to search in
        face_id         (required) – face ID (e.g. "BodyName_face_3")
        target_point    (required) – [x,y,z] in mm where the face center should go
        target_normal   (required) – [nx,ny,nz] direction the face should point
    """
    try:
        body_name = body.get("body_name")
        component_name = body.get("component")
        face_id = body.get("face_id")
        target_point = body.get("target_point")
        target_normal = body.get("target_normal")

        if not body_name:
            raise Exception("body_name is required")
        if not face_id:
            raise Exception("face_id is required")
        if not target_point:
            raise Exception("target_point [x,y,z] in mm is required")
        if not target_normal:
            raise Exception("target_normal [nx,ny,nz] is required")

        target_body = _find_body_by_name(body_name, component_name)

        # Resolve face via semantic selector first, then legacy index
        face = resolve_face_selector(face_id, target_body)
        src_centroid = _face_centroid(face)
        src_normal = _face_normal(face)
        src_frame = face_frame(face)

        tgt_origin = pt_mm(*target_point)
        tgt_normal = normalized(vec(*target_normal))
        tgt_frame = Frame.from_normal_and_point(tgt_origin, tgt_normal)

        # Compute the alignment transform
        matrix = align_transform(src_frame, tgt_frame)
        det = _check_rotation_matrix_det(matrix)

        # Extract axis-angle from the rotation part
        rotation_axis, rotation_angle, _ = _rotation_between_vectors(
            src_normal, tgt_normal)

        # Compute the translation (after rotation)
        # Translation = target_point - rotated_source_centroid
        translation_cm = matrix.translation
        translation_mm = [
            round(translation_cm.x * 10, 4),
            round(translation_cm.y * 10, 4),
            round(translation_cm.z * 10, 4),
        ]

        # Preview: where do all faces end up?
        faces_after = []
        for i in range(target_body.faces.count):
            f = target_body.faces.item(i)
            fc = _face_centroid(f)
            fn = _face_normal(f)

            # Apply the full matrix transform to centroid and normal
            new_c = pt(fc.x, fc.y, fc.z)
            new_c_p3d = adsk.core.Point3D.create(new_c.x, new_c.y, new_c.z)
            new_c_p3d.transformBy(matrix)

            # For the normal, transform by rotation only (no translation)
            rot_matrix = adsk.core.Matrix3D.create()
            for r in range(3):
                for c in range(3):
                    rot_matrix.setCell(r, c, matrix.getCell(r, c))
            new_n_p3d = adsk.core.Point3D.create(fn.x, fn.y, fn.z)
            new_n_p3d.transformBy(rot_matrix)
            new_normal_v = normalized(vec(new_n_p3d.x, new_n_p3d.y, new_n_p3d.z))

            new_axis_label = _snap_normal(new_normal_v)

            faces_after.append({
                "face_id": f"{body_name}_face_{i}",
                "new_centroid_mm": pt_to_mm(new_c_p3d),
                "new_normal": vec_to_list(new_normal_v),
                "new_direction": new_axis_label,
                "new_label": _semantic_label(new_axis_label, "plane"),
            })

        result = {
            "body": body_name,
            "face_id": face_id,
            "source_centroid_mm": pt_to_mm(src_centroid),
            "source_normal": vec_to_list(src_normal),
            "target_point_mm": target_point,
            "target_normal": target_normal,
            "rotation": {
                "axis": vec_to_list(rotation_axis),
                "angle_deg": round(math.degrees(rotation_angle), 4),
            },
            "translation_mm": translation_mm,
            "matrix": matrix_to_dict(matrix),
            "determinant": det,
            "is_proper_rotation": abs(det - 1.0) < 0.01,
            "faces_after": faces_after,
        }

        if abs(det - 1.0) > 0.01:
            result["warning"] = (
                f"Transform determinant is {det}, not +1. "
                f"This indicates a reflection is needed, which Fusion 360 "
                f"does NOT support. Suggestions: (1) Mirror the part design "
                f"in Fusion first, (2) Use joint-based placement via "
                f"/spatial_joint_to_point, (3) Use a two-step rotation."
            )
            # Try to find a two-step rotation alternative
            if abs(det + 1.0) < 0.01:
                result["alternative_two_step"] = (
                    "Try rotating 180 degrees around the normal axis first, "
                    "then apply the computed rotation. This avoids the "
                    "reflection by flipping the part the other way."
                )

        return result
    except Exception as e:
        return {"error": True, "message": str(e), "traceback": traceback.format_exc()}


# ── Find Placement Handler ───────────────────────────────────

def handle_spatial_find_placement(body):
    """Find a rotation that satisfies multiple face-placement constraints.

    Params:
        body_name    (required) – name of the body
        component    (optional) – component to search in
        placements   (required) – list of constraints, each:
            {
                "label": "outer" or "top" or etc.,
                "direction": "+X" or "-Z" or etc.,  (target direction for the face normal)
                "position": 225.0                    (optional: target coordinate in the direction axis, mm)
            }
            OR a string like "outer:+X@225, inner:-X@208, bottom:Z=0"
    """
    try:
        body_name = body.get("body_name")
        component_name = body.get("component")
        placements_raw = body.get("placements")

        if not body_name:
            raise Exception("body_name is required")
        if not placements_raw:
            raise Exception("placements is required")

        target_body = _find_body_by_name(body_name, component_name)

        # Parse placements
        constraints = []
        if isinstance(placements_raw, str):
            # Parse string format: "outer:+X@225, inner:-X@208, bottom:Z=0"
            for part in placements_raw.split(","):
                part = part.strip()
                if not part:
                    continue
                if ":" not in part:
                    raise Exception(
                        f"Invalid placement constraint: '{part}'. "
                        f"Use format: label:direction@position")
                label, rest = part.split(":", 1)
                label = label.strip()
                position = None
                if "@" in rest:
                    direction_str, pos_str = rest.split("@", 1)
                    position = float(pos_str.strip())
                elif "=" in rest:
                    direction_str, pos_str = rest.split("=", 1)
                    # Direction from axis letter
                    axis_letter = direction_str.strip()
                    if axis_letter in ("X", "Y", "Z"):
                        direction_str = f"+{axis_letter}"
                    position = float(pos_str.strip())
                else:
                    direction_str = rest.strip()
                constraints.append({
                    "label": label,
                    "direction": direction_str.strip(),
                    "position": position,
                })
        elif isinstance(placements_raw, list):
            constraints = placements_raw
        else:
            raise Exception("placements must be a string or list")

        # Classify all faces of the body
        face_map = {}
        for i in range(target_body.faces.count):
            f = target_body.faces.item(i)
            info = _classify_face(f, i, body_name)
            label = info["label"]
            if label not in face_map:
                face_map[label] = []
            face_map[label].append(info)

        # Direction string to unit vector
        dir_to_vec = {
            "+X": vec(1, 0, 0),  "-X": vec(-1, 0, 0),
            "+Y": vec(0, 1, 0),  "-Y": vec(0, -1, 0),
            "+Z": vec(0, 0, 1),  "-Z": vec(0, 0, -1),
        }

        # Try all 24 axis-aligned rotations (90-degree increments around X, Y, Z)
        # These are the only rotations that map axis-aligned faces to axis-aligned faces.
        candidate_rotations = []
        axes = [vec(1, 0, 0), vec(0, 1, 0), vec(0, 0, 1)]
        angles_deg = [0, 90, 180, 270]

        # Generate all 24 distinct orientations via combinations
        # Single-axis rotations
        for ax in axes:
            for ang in angles_deg:
                candidate_rotations.append((ax, ang))
        # Two-axis combinations for remaining orientations
        for ax1 in axes:
            for ang1 in [90, 270]:
                for ax2 in axes:
                    if vec_to_list(ax1) != vec_to_list(ax2):
                        for ang2 in [90, 180, 270]:
                            candidate_rotations.append(
                                ((ax1, ang1), (ax2, ang2)))

        best_match = None
        best_score = -1

        for rot in candidate_rotations:
            # Compute the rotation
            if isinstance(rot, tuple) and isinstance(rot[0], tuple):
                # Two-step rotation
                ax1, ang1 = rot[0]
                ax2, ang2 = rot[1]
                score = 0
                valid = True
                face_results = []

                for constraint in constraints:
                    c_label = constraint["label"]
                    c_dir = constraint["direction"]
                    if c_label not in face_map:
                        valid = False
                        break

                    target_vec = dir_to_vec.get(c_dir)
                    if not target_vec:
                        valid = False
                        break

                    # Check if any face with this label matches after rotation
                    matched = False
                    for face_info in face_map[c_label]:
                        n = vec(*face_info["normal"])
                        # Apply both rotations
                        n1 = _apply_rotation_to_vec(
                            ax1, math.radians(ang1), n)
                        n2 = _apply_rotation_to_vec(
                            ax2, math.radians(ang2), n1)
                        new_n = normalized(n2)
                        if dot(new_n, target_vec) > 0.95:
                            matched = True
                            face_results.append({
                                "label": c_label,
                                "face_id": face_info["face_id"],
                                "target_direction": c_dir,
                                "achieved_direction": _snap_normal(new_n),
                                "match": True,
                            })
                            score += 1
                            break
                    if not matched:
                        face_results.append({
                            "label": c_label,
                            "target_direction": c_dir,
                            "match": False,
                        })

                if score > best_score:
                    best_score = score
                    best_match = {
                        "type": "two_step",
                        "step1": {
                            "axis": vec_to_list(ax1),
                            "angle_deg": ang1,
                        },
                        "step2": {
                            "axis": vec_to_list(ax2),
                            "angle_deg": ang2,
                        },
                        "score": score,
                        "total_constraints": len(constraints),
                        "face_results": face_results,
                    }
            else:
                # Single rotation
                ax, ang = rot
                score = 0
                face_results = []

                for constraint in constraints:
                    c_label = constraint["label"]
                    c_dir = constraint["direction"]
                    if c_label not in face_map:
                        face_results.append({
                            "label": c_label,
                            "target_direction": c_dir,
                            "match": False,
                            "reason": f"No face with label '{c_label}' found",
                        })
                        continue

                    target_vec = dir_to_vec.get(c_dir)
                    if not target_vec:
                        face_results.append({
                            "label": c_label,
                            "target_direction": c_dir,
                            "match": False,
                            "reason": f"Unknown direction '{c_dir}'",
                        })
                        continue

                    matched = False
                    for face_info in face_map[c_label]:
                        n = vec(*face_info["normal"])
                        new_n = _apply_rotation_to_vec(
                            ax, math.radians(ang), n)
                        new_n = normalized(new_n)
                        if dot(new_n, target_vec) > 0.95:
                            matched = True
                            face_results.append({
                                "label": c_label,
                                "face_id": face_info["face_id"],
                                "target_direction": c_dir,
                                "achieved_direction": _snap_normal(new_n),
                                "match": True,
                            })
                            score += 1
                            break

                    if not matched:
                        face_results.append({
                            "label": c_label,
                            "target_direction": c_dir,
                            "match": False,
                        })

                if score > best_score:
                    best_score = score
                    best_match = {
                        "type": "single",
                        "axis": vec_to_list(ax),
                        "angle_deg": ang,
                        "score": score,
                        "total_constraints": len(constraints),
                        "face_results": face_results,
                    }

        all_matched = best_score == len(constraints)

        result = {
            "body": body_name,
            "constraints": constraints,
            "face_map_labels": list(face_map.keys()),
            "best_rotation": best_match,
            "all_constraints_satisfied": all_matched,
        }

        if not all_matched:
            result["suggestions"] = [
                "No single axis-aligned rotation satisfies all constraints.",
                "Consider: (1) Mirror the part design if a reflection is needed.",
                "(2) Use /spatial_joint_to_point for joint-based placement.",
                "(3) Use /spatial_find_transform to align one face and adjust from there.",
                f"Best match satisfied {best_score}/{len(constraints)} constraints.",
            ]

        return result
    except Exception as e:
        return {"error": True, "message": str(e), "traceback": traceback.format_exc()}


# ── Joint-Based Placement Handlers ──────────────────────────

def handle_spatial_joint_placement(body):
    """Place an occurrence using Fusion's Joint system — bypasses rotation math.

    Params:
        occurrence         (required) – occurrence name (e.g. "BT_LeftPanel:1")
        source_face        (required) – face ID on the occurrence's component
        target_face        (optional) – face ID on target component
        target_component   (optional) – component containing the target face
        target_point       (optional) – [x,y,z] in mm (alternative to target_face)
        target_normal      (optional) – [nx,ny,nz] (used with target_point)
        joint_type         (optional) – default "rigid"
        name               (optional) – joint name
    """
    try:
        root = get_root()

        occ_name = body.get("occurrence")
        if not occ_name:
            raise Exception("occurrence is required")

        source_face_id = body.get("source_face")
        if not source_face_id:
            raise Exception("source_face is required")

        target_face_id = body.get("target_face")
        target_comp_name = body.get("target_component")
        target_point = body.get("target_point")
        target_normal = body.get("target_normal")
        joint_type_str = body.get("joint_type", "rigid")
        joint_name = body.get("name")

        # Find the occurrence
        occ = None
        for i in range(root.allOccurrences.count):
            o = root.allOccurrences.item(i)
            if o.name == occ_name or occ_name.lower() in o.name.lower():
                occ = o
                break
        if not occ:
            names = [root.allOccurrences.item(i).name
                     for i in range(root.allOccurrences.count)]
            raise Exception(
                f"Occurrence '{occ_name}' not found. Available: {names}")

        # Find the source face
        comp = occ.component
        src_face = _resolve_face(comp, source_face_id)

        # Build geometry1 from source face
        geo1 = adsk.fusion.JointGeometry.createByPlanarFace(
            src_face, None,
            adsk.fusion.JointKeyPointTypes.MiddleKeyPoint)

        # Build geometry2
        if target_face_id and target_comp_name:
            target_comp, target_occ = get_component_by_name(target_comp_name)
            if not target_comp:
                available = _all_component_names(root)
                raise Exception(
                    f"Target component '{target_comp_name}' not found. "
                    f"Available: {available}")
            tgt_face = _resolve_face(target_comp, target_face_id)
            geo2 = adsk.fusion.JointGeometry.createByPlanarFace(
                tgt_face, None,
                adsk.fusion.JointKeyPointTypes.MiddleKeyPoint)
        elif target_point:
            # Create a construction point at the target
            cp = root.constructionPoints
            cpi = cp.createInput()
            cpi.setByPoint(adsk.core.Point3D.create(
                target_point[0] / 10.0,
                target_point[1] / 10.0,
                target_point[2] / 10.0))
            point = cp.add(cpi)
            geo2 = adsk.fusion.JointGeometry.createByPoint(point)
        else:
            raise Exception(
                "Either target_face+target_component or target_point is required")

        # Create the joint
        type_map = {
            "rigid": adsk.fusion.JointTypes.RigidJointType,
            "revolute": adsk.fusion.JointTypes.RevoluteJointType,
            "slider": adsk.fusion.JointTypes.SliderJointType,
            "planar": adsk.fusion.JointTypes.PlanarJointType,
            "ball": adsk.fusion.JointTypes.BallJointType,
        }
        joint_type = type_map.get(joint_type_str)
        if not joint_type:
            raise Exception(
                f"Unknown joint type: {joint_type_str}. "
                f"Valid: {list(type_map.keys())}")

        joints = root.joints
        joint_input = joints.createInput(geo1, geo2)
        if joint_type_str == "rigid":
            joint_input.setAsRigidJointMotion()

        joint = joints.add(joint_input)
        if joint_name:
            joint.name = joint_name
        adsk.doEvents()

        # Report result
        bbox = occ.boundingBox
        return {
            "success": True,
            "occurrence": occ.name,
            "joint_name": joint.name,
            "joint_type": joint_type_str,
            "bounding_box_mm": {
                "min": pt_to_mm(bbox.minPoint),
                "max": pt_to_mm(bbox.maxPoint),
            },
            "message": f"Placed '{occ.name}' via joint '{joint.name}'",
        }
    except Exception as e:
        return {"error": True, "message": str(e), "traceback": traceback.format_exc()}


def handle_spatial_joint_to_point(body):
    """Place an occurrence face at a target point + normal via joints.

    This is the simplest way to position a component: specify which face
    should go where, and Fusion handles the rotation math natively.

    Params:
        occurrence      (required) – occurrence name
        face_id         (required) – face on the occurrence (e.g. "PanelBody_face_2")
        target_normal   (required) – [nx,ny,nz] direction the face should point

        Positioning (use ONE of these):
        face_at         (preferred) – "X=225" or "Z=579" — puts the face SURFACE at this coordinate.
                         Automatically computes the centroid offset. Intuitive for placing panels.
        target_point    (fallback) – [x,y,z] in mm — puts the face CENTROID at this exact point.

        source_up       (optional) – [x,y,z] part direction that should map to assembly "up"
        up_direction    (optional) – [x,y,z] assembly "up" direction after placement
        joint_name      (optional) – name for the joint
    """
    try:
        root = get_root()
        design = get_design()

        occ_name = body.get("occurrence")
        face_id = body.get("face_id")
        target_point = body.get("target_point")
        target_normal = body.get("target_normal")
        face_at = body.get("face_at")
        j_name = body.get("joint_name")
        lock = body.get("lock", False)

        if not occ_name:
            raise Exception("occurrence is required")
        if not face_id:
            raise Exception("face_id is required")
        if not target_normal:
            raise Exception("target_normal [nx,ny,nz] is required")
        if not target_point and not face_at:
            raise Exception(
                "Either target_point [x,y,z] or face_at 'AXIS=VALUE' is required. "
                "face_at places the face SURFACE at a coordinate (e.g. 'X=225'). "
                "target_point places the face CENTROID at an exact point.")

        # Find the occurrence
        occ = None
        for i in range(root.allOccurrences.count):
            o = root.allOccurrences.item(i)
            if o.name == occ_name or occ_name.lower() in o.name.lower():
                occ = o
                break
        if not occ:
            names = [root.allOccurrences.item(i).name
                     for i in range(root.allOccurrences.count)]
            raise Exception(
                f"Occurrence '{occ_name}' not found. Available: {names}")

        comp = occ.component
        face = _resolve_face(comp, face_id)

        # Handle face_at: compute target_point from face surface position
        # face_at specifies WHERE the face surface should end up in assembly coords.
        # It works by:
        # 1. Finding the face's offset from the body center (in the face normal direction)
        # 2. Computing the body center position that puts the face surface at the requested coordinate
        # 3. For unspecified axes, the body center defaults to 0 (assembly origin)
        #
        # Multiple axes: "X=225,Z=289.5" or just "X=225"
        if face_at and not target_point:
            # Get the body's bounding box to find dimensions and center
            target_body = None
            for b in comp.bRepBodies:
                for fi in range(b.faces.count):
                    if b.faces.item(fi) == face:
                        target_body = b
                        break
                if target_body:
                    break
            if not target_body:
                for b in comp.bRepBodies:
                    target_body = b
                    break

            bbox = target_body.boundingBox
            body_center_mm = [
                (bbox.minPoint.x + bbox.maxPoint.x) / 2.0 * 10,
                (bbox.minPoint.y + bbox.maxPoint.y) / 2.0 * 10,
                (bbox.minPoint.z + bbox.maxPoint.z) / 2.0 * 10,
            ]
            body_half_dims_mm = [
                (bbox.maxPoint.x - bbox.minPoint.x) / 2.0 * 10,
                (bbox.maxPoint.y - bbox.minPoint.y) / 2.0 * 10,
                (bbox.maxPoint.z - bbox.minPoint.z) / 2.0 * 10,
            ]

            # Face centroid (where the face surface is in part coords)
            face_centroid = _face_centroid(face)
            face_centroid_mm = [face_centroid.x * 10, face_centroid.y * 10, face_centroid.z * 10]

            # Face normal tells us which direction the face offset is in
            fn = _face_normal(face)
            face_normal_mm = [fn.x, fn.y, fn.z]

            # The face surface offset from body center along the face normal
            face_offset_from_center = sum(
                (face_centroid_mm[i] - body_center_mm[i]) * face_normal_mm[i]
                for i in range(3))

            # Parse face_at constraints: "X=225" or "X=225,Z=289.5"
            constraints = {}
            for part in str(face_at).split(","):
                part = part.strip()
                if "=" not in part:
                    raise Exception(
                        f"face_at must be 'AXIS=VALUE' (e.g. 'X=225'). Got: '{part}'")
                ax, val = part.split("=", 1)
                ax = ax.strip().upper()
                if ax not in ("X", "Y", "Z"):
                    raise Exception(f"face_at axis must be X, Y, or Z. Got: '{ax}'")
                constraints[ax] = float(val.strip())

            # Build target_point: for each constrained axis, compute body center position
            # that puts the face surface at the requested coordinate.
            # For unconstrained axes, default to 0 (assembly origin center).
            tgt_n = normalized(vec(*target_normal))
            target_point = [0.0, 0.0, 0.0]

            # The source frame origin is the face centroid.
            # align_transform maps source_origin → target_origin.
            # For the axis aligned with face normal: target_point = constraint value
            #   (face centroid IS on the surface, so no offset needed)
            # For OTHER axes: the face centroid may not be at the body center
            #   (e.g. rabbet cuts shift the centroid). We need to offset so the
            #   BODY center lands at the constraint value, not the face centroid.
            face_centroid_mm = [face_centroid.x * 10, face_centroid.y * 10, face_centroid.z * 10]
            tgt_n_list = [tgt_n.x, tgt_n.y, tgt_n.z]

            for ax, idx in [("X", 0), ("Y", 1), ("Z", 2)]:
                if ax in constraints:
                    # Is this axis aligned with the face normal?
                    if abs(tgt_n_list[idx]) > 0.5:
                        # Normal axis: face surface goes directly to the constraint
                        target_point[idx] = constraints[ax]
                    else:
                        # Non-normal axis: offset so body center lands at constraint
                        # face_centroid is offset from body_center by some amount
                        centroid_offset = face_centroid_mm[idx] - body_center_mm[idx]
                        target_point[idx] = constraints[ax] + centroid_offset

        # Build source and target frames
        # Source frame: face normal is Z, need to determine X and Y
        src_normal = normalized(_face_normal(face))
        src_centroid = _face_centroid(face)

        source_up = body.get("source_up")  # direction in PART that should map to target up
        up_dir = body.get("up_direction")  # direction in ASSEMBLY for "up" after placement

        if source_up:
            # User specifies which part direction should map to "up"
            src_up_vec = normalized(vec(*source_up))
            # Project src_up onto the plane perpendicular to the face normal
            d = dot(src_up_vec, src_normal)
            src_x = normalized(vec(
                src_up_vec.x - d * src_normal.x,
                src_up_vec.y - d * src_normal.y,
                src_up_vec.z - d * src_normal.z))
            src_y = normalized(cross(src_normal, src_x))
            src_frame = Frame(src_centroid, src_x, src_y, src_normal)
        else:
            src_frame = face_frame(face)

        tgt_origin = pt_mm(*target_point)
        tgt_normal_vec = normalized(vec(*target_normal))

        if up_dir:
            # User specifies assembly up direction
            tgt_up_vec = normalized(vec(*up_dir))
            # Project onto plane perpendicular to target normal
            d = dot(tgt_up_vec, tgt_normal_vec)
            tgt_x = normalized(vec(
                tgt_up_vec.x - d * tgt_normal_vec.x,
                tgt_up_vec.y - d * tgt_normal_vec.y,
                tgt_up_vec.z - d * tgt_normal_vec.z))
            tgt_y = normalized(cross(tgt_normal_vec, tgt_x))
            tgt_frame = Frame(tgt_origin, tgt_x, tgt_y, tgt_normal_vec)
        else:
            tgt_frame = Frame.from_normal_and_point(tgt_origin, tgt_normal_vec)

        matrix = align_transform(src_frame, tgt_frame)

        # Check determinant
        det = _check_rotation_matrix_det(matrix)
        if abs(det - 1.0) > 0.01:
            return {
                "error": True,
                "message": (
                    f"Transform requires reflection (det={det}). "
                    f"Fusion 360 does not support reflection transforms. "
                    f"Suggestions: (1) Mirror the part design first. "
                    f"(2) Flip the target_normal. "
                    f"(3) Use a different face as source."),
                "determinant": det,
                "source_face": face_id,
                "source_normal": vec_to_list(_face_normal(face)),
                "target_normal": target_normal,
            }

        apply_transform_to_occurrence(occ, matrix)
        adsk.doEvents()

        # Lock position via grounding so it persists across save/reopen
        if lock:
            occ.isGrounded = True
            adsk.doEvents()

        bbox = occ.boundingBox
        return {
            "success": True,
            "occurrence": occ.name,
            "face_id": face_id,
            "target_point_mm": target_point,
            "target_normal": target_normal,
            "determinant": det,
            "locked": bool(lock),
            "transform": matrix_to_dict(matrix),
            "bounding_box_mm": {
                "min": pt_to_mm(bbox.minPoint),
                "max": pt_to_mm(bbox.maxPoint),
            },
            "message": (
                f"Placed '{occ.name}' with face '{face_id}' "
                f"at {target_point} facing {target_normal}"
                f"{' (locked)' if lock else ''}"),
        }
    except Exception as e:
        return {"error": True, "message": str(e), "traceback": traceback.format_exc()}


def _resolve_face(comp, face_id):
    """Resolve a face_id string to a BRepFace on a component.

    Tries semantic selectors first (e.g. 'largest:+Z', '+X', 'miter'),
    then falls back to legacy face ID (Body_face_N) or plain index.
    """
    # Try semantic selector on each body in the component
    for b in comp.bRepBodies:
        try:
            result = select_face(face_id, b)
            if result is not None:
                return result
        except Exception:
            # Selector matched a pattern but no face found on this body;
            # continue to next body before giving up
            continue

    # Legacy resolution: index-based
    face_idx = None
    if "_face_" in face_id:
        parts = face_id.rsplit("_face_", 1)
        try:
            face_idx = int(parts[1])
        except ValueError:
            pass
        # Try to match body name
        body_hint = parts[0] if face_idx is not None else None
    else:
        try:
            face_idx = int(face_id)
        except ValueError:
            pass
        body_hint = None

    if face_idx is not None:
        if body_hint:
            for b in comp.bRepBodies:
                if b.name == body_hint and face_idx < b.faces.count:
                    return b.faces.item(face_idx)
        # Fallback: search all bodies
        for b in comp.bRepBodies:
            if face_idx < b.faces.count:
                return b.faces.item(face_idx)

    available = []
    for b in comp.bRepBodies:
        for i in range(b.faces.count):
            available.append(f"{b.name}_face_{i}")
    raise Exception(
        f"Face '{face_id}' not found. Available: {available[:20]}")


# ── Declarative Placement Handler ────────────────────────────

def _parse_axis_constraint(constraint_str):
    """Parse a constraint string like 'X=225' or 'Z=0:579'.

    Returns (axis_letter, value, range_min, range_max).
    For single value: range_min and range_max are both None.
    For range: value is the midpoint.
    """
    constraint_str = constraint_str.strip()
    if "=" not in constraint_str:
        raise Exception(
            f"Invalid constraint '{constraint_str}'. "
            f"Use 'AXIS=VALUE' (e.g. 'X=225') or 'AXIS=MIN:MAX' (e.g. 'Z=0:579').")
    axis_letter, rest = constraint_str.split("=", 1)
    axis_letter = axis_letter.strip().upper()
    if axis_letter not in ("X", "Y", "Z"):
        raise Exception(
            f"Axis must be X, Y, or Z. Got: '{axis_letter}'")
    rest = rest.strip()
    if ":" in rest:
        parts = rest.split(":", 1)
        range_min = float(parts[0].strip())
        range_max = float(parts[1].strip())
        value = (range_min + range_max) / 2.0
        return axis_letter, value, range_min, range_max
    else:
        value = float(rest)
        return axis_letter, value, None, None


def _axis_letter_to_index(letter):
    return {"X": 0, "Y": 1, "Z": 2}[letter]


def _axis_letter_to_vec(letter, positive=True):
    sign = 1.0 if positive else -1.0
    if letter == "X":
        return vec(sign, 0, 0)
    elif letter == "Y":
        return vec(0, sign, 0)
    else:
        return vec(0, 0, sign)


def handle_declarative_place(body):
    """Place an occurrence using declarative constraints.

    Instead of specifying rotation math, describe WHERE each logical
    face should go. The handler figures out the rotation automatically.

    Params:
        occurrence   (required) -- occurrence name
        outer_at     (required) -- "X=225" or "Z=579" -- where the outer face goes
        height       (optional) -- "Z=0:579" -- axis and range for height direction
        depth        (optional) -- "Y=-200:200" -- axis and range for depth direction
        ground       (optional, default true) -- ground the component after placement
    """
    try:
        root = get_root()

        occ_name = body.get("occurrence")
        outer_at_str = body.get("outer_at")
        height_str = body.get("height")
        depth_str = body.get("depth")
        should_ground = body.get("ground", True)

        if not occ_name:
            raise Exception("occurrence is required")
        if not outer_at_str:
            raise Exception(
                "outer_at is required (e.g. 'X=225' — where the outer face surface goes)")

        # Find occurrence
        occ = None
        for i in range(root.allOccurrences.count):
            o = root.allOccurrences.item(i)
            if o.name == occ_name or occ_name.lower() in o.name.lower():
                occ = o
                break
        if not occ:
            names = [root.allOccurrences.item(i).name
                     for i in range(root.allOccurrences.count)]
            raise Exception(
                f"Occurrence '{occ_name}' not found. Available: {names}")

        comp = occ.component

        # Find the body (use first body with faces)
        target_body = None
        for b in comp.bRepBodies:
            if b.faces.count > 0:
                target_body = b
                break
        if not target_body:
            raise Exception(
                f"No body with faces found in component '{comp.name}'")

        # Step 1: Build face map — find largest face (outer), and body dimensions
        bbox = target_body.boundingBox
        body_min_mm = [bbox.minPoint.x * 10, bbox.minPoint.y * 10, bbox.minPoint.z * 10]
        body_max_mm = [bbox.maxPoint.x * 10, bbox.maxPoint.y * 10, bbox.maxPoint.z * 10]
        body_dims_mm = [body_max_mm[i] - body_min_mm[i] for i in range(3)]
        body_center_mm = [(body_min_mm[i] + body_max_mm[i]) / 2.0 for i in range(3)]

        # Sort dimensions to determine height (longest), depth (second), thickness (smallest)
        dim_indices = sorted(range(3), key=lambda i: body_dims_mm[i], reverse=True)
        height_src_idx = dim_indices[0]  # longest = height
        depth_src_idx = dim_indices[1]   # second = depth
        thickness_src_idx = dim_indices[2]  # smallest = thickness (outer normal direction)

        # Source axes in part space: X=0, Y=1, Z=2
        src_axes = [vec(1, 0, 0), vec(0, 1, 0), vec(0, 0, 1)]

        # Find the outer face: largest face, whose normal is along the thickness axis
        outer_face = select_face(f"largest:{_snap_normal(src_axes[thickness_src_idx])}", target_body)
        if not outer_face:
            # Try negative direction
            outer_face = select_face(
                f"largest:{_snap_normal(negated(src_axes[thickness_src_idx]))}",
                target_body)
        if not outer_face:
            raise Exception(
                f"Cannot find outer face on body '{target_body.name}'. "
                f"Body dims: {[round(d, 2) for d in body_dims_mm]}")

        outer_normal = _face_normal(outer_face)
        outer_dir = _snap_normal(outer_normal)

        # Step 2: Parse constraints
        outer_axis, outer_value, _, _ = _parse_axis_constraint(outer_at_str)
        outer_tgt_idx = _axis_letter_to_index(outer_axis)

        height_tgt_idx = None
        height_range = None
        if height_str:
            h_axis, h_mid, h_min, h_max = _parse_axis_constraint(height_str)
            height_tgt_idx = _axis_letter_to_index(h_axis)
            if h_min is not None:
                height_range = (h_min, h_max)

        depth_tgt_idx = None
        depth_range = None
        if depth_str:
            d_axis, d_mid, d_min, d_max = _parse_axis_constraint(depth_str)
            depth_tgt_idx = _axis_letter_to_index(d_axis)
            if d_min is not None:
                depth_range = (d_min, d_max)

        # If height/depth not specified, infer from remaining axes
        used_axes = {outer_tgt_idx}
        if height_tgt_idx is not None:
            used_axes.add(height_tgt_idx)
        if depth_tgt_idx is not None:
            used_axes.add(depth_tgt_idx)

        remaining = [i for i in range(3) if i not in used_axes]
        if height_tgt_idx is None and remaining:
            # Pick the axis not used by outer/depth — prefer Z for height
            if 2 in remaining:
                height_tgt_idx = 2
            else:
                height_tgt_idx = remaining[0]
            remaining.remove(height_tgt_idx)
        if depth_tgt_idx is None and remaining:
            depth_tgt_idx = remaining[0]

        # Step 3: Build rotation matrix
        # Source directions (in part coords)
        src_outer = normalized(outer_normal)  # thickness direction
        src_height = src_axes[height_src_idx]   # longest dim direction
        src_depth = src_axes[depth_src_idx]     # second dim direction

        # Target directions (in assembly coords)
        # Outer normal should point in the direction of outer_axis
        tgt_outer = _axis_letter_to_vec(outer_axis, positive=True)
        tgt_height = src_axes[height_tgt_idx] if height_tgt_idx is not None else vec(0, 0, 1)
        tgt_depth = src_axes[depth_tgt_idx] if depth_tgt_idx is not None else vec(0, 1, 0)

        # Build 3x3 rotation: maps [src_outer, src_height, src_depth] -> [tgt_outer, tgt_height, tgt_depth]
        # Each source vector should map to corresponding target vector.
        # R * src_outer = tgt_outer, R * src_height = tgt_height, R * src_depth = tgt_depth
        # R = T * S^-1 where S = [src columns], T = [tgt columns]

        def _vec_components(v):
            return [v.x, v.y, v.z]

        S = [_vec_components(src_outer), _vec_components(src_height), _vec_components(src_depth)]
        T = [_vec_components(tgt_outer), _vec_components(tgt_height), _vec_components(tgt_depth)]

        # S and T are 3x3 matrices where columns are the vectors
        # R = T * S^(-1)
        # Since source vectors are axis-aligned, S^-1 is just the transpose
        # (columns of S form an orthonormal-ish basis)

        # Compute determinant of S to check orientation
        def _det3(m):
            return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
                    - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                    + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))

        # Transpose for column-major
        S_cols = [[S[j][i] for j in range(3)] for i in range(3)]
        T_cols = [[T[j][i] for j in range(3)] for i in range(3)]

        det_s = _det3(S_cols)
        det_t = _det3(T_cols)

        # If determinants have opposite sign, we need a reflection fix
        if det_s * det_t < 0:
            # Flip the source depth direction to fix the orientation
            src_depth = negated(src_depth)
            S[2] = _vec_components(src_depth)
            S_cols = [[S[j][i] for j in range(3)] for i in range(3)]

        # Compute R = T_cols * inv(S_cols)
        # For orthonormal bases, inv = transpose
        def _mat_mul(A, B):
            result = [[0.0] * 3 for _ in range(3)]
            for i in range(3):
                for j in range(3):
                    for k in range(3):
                        result[i][j] += A[i][k] * B[k][j]
            return result

        def _transpose(M):
            return [[M[j][i] for j in range(3)] for i in range(3)]

        S_inv = _transpose(S_cols)
        R = _mat_mul(T_cols, S_inv)

        # Verify determinant is +1
        det_r = _det3(R)
        if abs(det_r - 1.0) > 0.1:
            # Try flipping src_height too
            src_height = negated(src_height)
            S[1] = _vec_components(src_height)
            S_cols = [[S[j][i] for j in range(3)] for i in range(3)]
            S_inv = _transpose(S_cols)
            R = _mat_mul(T_cols, S_inv)
            det_r = _det3(R)

        # Step 4: Compute translation
        # After rotation, the body center moves to R * body_center
        # We want:
        #   - outer face surface at outer_value on outer_axis
        #   - body center on height axis at midpoint of height_range (or 0)
        #   - body center on depth axis at midpoint of depth_range (or 0)

        # Rotated body center
        rotated_center = [0.0, 0.0, 0.0]
        for i in range(3):
            for j in range(3):
                rotated_center[i] += R[i][j] * (body_center_mm[j] / 10.0)  # cm
            rotated_center[i] *= 10.0  # back to mm

        # Rotated body half-dims along each target axis
        # The outer face offset from center along outer axis
        face_centroid = _face_centroid(outer_face)
        face_centroid_mm = [face_centroid.x * 10, face_centroid.y * 10, face_centroid.z * 10]

        # Rotated face centroid
        rotated_face = [0.0, 0.0, 0.0]
        for i in range(3):
            for j in range(3):
                rotated_face[i] += R[i][j] * (face_centroid_mm[j] / 10.0)
            rotated_face[i] *= 10.0

        # Translation: shift so rotated face centroid[outer_axis] = outer_value
        translation_mm = [0.0, 0.0, 0.0]
        translation_mm[outer_tgt_idx] = outer_value - rotated_face[outer_tgt_idx]

        if height_range is not None and height_tgt_idx is not None:
            h_mid = (height_range[0] + height_range[1]) / 2.0
            translation_mm[height_tgt_idx] = h_mid - rotated_center[height_tgt_idx]

        if depth_range is not None and depth_tgt_idx is not None:
            d_mid = (depth_range[0] + depth_range[1]) / 2.0
            translation_mm[depth_tgt_idx] = d_mid - rotated_center[depth_tgt_idx]

        # Step 5: Build Matrix3D and apply
        matrix = adsk.core.Matrix3D.create()
        for i in range(3):
            for j in range(3):
                matrix.setCell(i, j, R[i][j])
        # Set translation (in cm)
        trans_vec = adsk.core.Vector3D.create(
            translation_mm[0] / 10.0,
            translation_mm[1] / 10.0,
            translation_mm[2] / 10.0)
        matrix.translation = trans_vec

        apply_transform_to_occurrence(occ, matrix)
        adsk.doEvents()

        # Step 6: Ground the occurrence if requested
        if should_ground:
            occ.isGrounded = True

        final_bbox = occ.boundingBox
        return {
            "success": True,
            "occurrence": occ.name,
            "outer_at": outer_at_str,
            "height": height_str,
            "depth": depth_str,
            "grounded": should_ground,
            "rotation_determinant": round(det_r, 4),
            "translation_mm": [round(v, 4) for v in translation_mm],
            "bounding_box_mm": {
                "min": pt_to_mm(final_bbox.minPoint),
                "max": pt_to_mm(final_bbox.maxPoint),
            },
            "message": (
                f"Placed '{occ.name}' with outer face at {outer_at_str}"
                + (f", height={height_str}" if height_str else "")
                + (f", depth={depth_str}" if depth_str else "")
                + (", grounded" if should_ground else "")),
        }
    except Exception as e:
        return {"error": True, "message": str(e), "traceback": traceback.format_exc()}


# ── Route table ──────────────────────────────────────────────

SPATIAL_ROUTES = {
    # Spatial Queries (read-only)
    "/spatial_face_map": handle_spatial_face_map,
    "/spatial_transform_preview": handle_spatial_transform_preview,
    "/spatial_find_transform": handle_spatial_find_transform,
    "/spatial_find_placement": handle_spatial_find_placement,
    # Joint-Based Placement
    "/spatial_joint_placement": handle_spatial_joint_placement,
    "/spatial_joint_to_point": handle_spatial_joint_to_point,
    # Declarative Placement
    "/spatial_declarative_place": handle_declarative_place,
}
