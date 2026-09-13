"""Form (T-Spline/Sculpt) handlers for Fusion MCP Bridge.

Creates and manages T-Spline form features for organic modeling.
Primitives are created via TSM (T-Spline Mesh) descriptions because the
Fusion API exposes form creation through TSplineBodies.addByTSMDescription().

Each handler has the signature handle_*(body: dict) -> dict
and is registered in FORM_ROUTES.
"""
import math
import os
import tempfile

import adsk.core
import adsk.fusion

try:
    from bridge_helpers import get_root, get_design, current_design_type, assert_parametric
except ImportError:
    from .bridge_helpers import get_root, get_design, current_design_type, assert_parametric


# ── TSM primitive generators ────────────────────────────────

def _tsm_box(lx, ly, lz, cx=0, cy=0, cz=0):
    """Generate TSM description for a box centered at (cx,cy,cz)."""
    hx, hy, hz = lx / 2, ly / 2, lz / 2
    verts = [
        (cx - hx, cy - hy, cz - hz), (cx + hx, cy - hy, cz - hz),
        (cx + hx, cy + hy, cz - hz), (cx - hx, cy + hy, cz - hz),
        (cx - hx, cy - hy, cz + hz), (cx + hx, cy - hy, cz + hz),
        (cx + hx, cy + hy, cz + hz), (cx - hx, cy + hy, cz + hz),
    ]
    faces = [
        (0, 3, 2, 1), (4, 5, 6, 7),  # bottom, top
        (0, 1, 5, 4), (2, 3, 7, 6),  # front, back
        (1, 2, 6, 5), (0, 4, 7, 3),  # right, left
    ]
    lines = ["TSM_Version 2 0"]
    lines.append(f"Vertices {len(verts)}")
    for v in verts:
        lines.append(f"  {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}")
    lines.append(f"Faces {len(faces)}")
    for f in faces:
        lines.append(f"  {len(f)} " + " ".join(str(i) for i in f))
    lines.append("End")
    return "\n".join(lines)


def _tsm_cylinder(radius, height, radial=8, cx=0, cy=0, cz=0):
    """Generate TSM description for a cylinder along Z axis."""
    verts = []
    # Bottom ring
    for i in range(radial):
        angle = 2 * math.pi * i / radial
        verts.append((cx + radius * math.cos(angle),
                       cy + radius * math.sin(angle), cz))
    # Top ring
    for i in range(radial):
        angle = 2 * math.pi * i / radial
        verts.append((cx + radius * math.cos(angle),
                       cy + radius * math.sin(angle), cz + height))

    faces = []
    # Side quads
    for i in range(radial):
        n = (i + 1) % radial
        faces.append((i, n, n + radial, i + radial))
    # Bottom and top n-gon
    faces.append(tuple(range(radial - 1, -1, -1)))
    faces.append(tuple(range(radial, 2 * radial)))

    lines = ["TSM_Version 2 0"]
    lines.append(f"Vertices {len(verts)}")
    for v in verts:
        lines.append(f"  {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}")
    lines.append(f"Faces {len(faces)}")
    for f in faces:
        lines.append(f"  {len(f)} " + " ".join(str(i) for i in f))
    lines.append("End")
    return "\n".join(lines)


def _tsm_sphere(radius, cx=0, cy=0, cz=0):
    """Generate TSM description for a sphere (cube-sphere topology)."""
    # Use a simple cube topology that subdivides into a sphere
    r = radius
    verts = [
        (cx - r, cy - r, cz - r), (cx + r, cy - r, cz - r),
        (cx + r, cy + r, cz - r), (cx - r, cy + r, cz - r),
        (cx - r, cy - r, cz + r), (cx + r, cy - r, cz + r),
        (cx + r, cy + r, cz + r), (cx - r, cy + r, cz + r),
    ]
    # Normalize to sphere surface
    for i, (x, y, z) in enumerate(verts):
        dx, dy, dz = x - cx, y - cy, z - cz
        mag = math.sqrt(dx * dx + dy * dy + dz * dz)
        verts[i] = (cx + dx / mag * r, cy + dy / mag * r, cz + dz / mag * r)
    faces = [
        (0, 3, 2, 1), (4, 5, 6, 7),
        (0, 1, 5, 4), (2, 3, 7, 6),
        (1, 2, 6, 5), (0, 4, 7, 3),
    ]
    lines = ["TSM_Version 2 0"]
    lines.append(f"Vertices {len(verts)}")
    for v in verts:
        lines.append(f"  {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}")
    lines.append(f"Faces {len(faces)}")
    for f in faces:
        lines.append(f"  {len(f)} " + " ".join(str(i) for i in f))
    lines.append("End")
    return "\n".join(lines)


def _tsm_torus(major_radius, minor_radius, radial=12, tubular=8, cx=0, cy=0, cz=0):
    """Generate TSM description for a torus lying on the XY plane."""
    verts = []
    for i in range(radial):
        theta = 2 * math.pi * i / radial
        for j in range(tubular):
            phi = 2 * math.pi * j / tubular
            x = cx + (major_radius + minor_radius * math.cos(phi)) * math.cos(theta)
            y = cy + (major_radius + minor_radius * math.cos(phi)) * math.sin(theta)
            z = cz + minor_radius * math.sin(phi)
            verts.append((x, y, z))

    faces = []
    for i in range(radial):
        ni = (i + 1) % radial
        for j in range(tubular):
            nj = (j + 1) % tubular
            faces.append((
                i * tubular + j,
                ni * tubular + j,
                ni * tubular + nj,
                i * tubular + nj,
            ))

    lines = ["TSM_Version 2 0"]
    lines.append(f"Vertices {len(verts)}")
    for v in verts:
        lines.append(f"  {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}")
    lines.append(f"Faces {len(faces)}")
    for f in faces:
        lines.append(f"  {len(f)} " + " ".join(str(i) for i in f))
    lines.append("End")
    return "\n".join(lines)


def _tsm_pipe(outer_radius, inner_radius, height, radial=8, cx=0, cy=0, cz=0):
    """Generate TSM description for a hollow pipe (tube) along Z axis."""
    verts = []
    # Bottom outer ring, bottom inner ring, top outer ring, top inner ring
    for z_off, r in [(0, outer_radius), (0, inner_radius),
                     (height, outer_radius), (height, inner_radius)]:
        for i in range(radial):
            angle = 2 * math.pi * i / radial
            verts.append((cx + r * math.cos(angle),
                          cy + r * math.sin(angle),
                          cz + z_off))

    faces = []
    bo, bi, to, ti = 0, radial, 2 * radial, 3 * radial
    for i in range(radial):
        n = (i + 1) % radial
        # Outer wall
        faces.append((bo + i, bo + n, to + n, to + i))
        # Inner wall (reversed winding)
        faces.append((bi + i, ti + i, ti + n, bi + n))
        # Top annular face
        faces.append((to + i, to + n, ti + n, ti + i))
        # Bottom annular face (reversed)
        faces.append((bo + i, bi + i, bi + n, bo + n))

    lines = ["TSM_Version 2 0"]
    lines.append(f"Vertices {len(verts)}")
    for v in verts:
        lines.append(f"  {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}")
    lines.append(f"Faces {len(faces)}")
    for f in faces:
        lines.append(f"  {len(f)} " + " ".join(str(i) for i in f))
    lines.append("End")
    return "\n".join(lines)


# ── Helpers ──────────────────────────────────────────────────

def _get_form_feature(root, feature_id):
    """Resolve a form feature by name or index."""
    forms = root.features.formFeatures
    if feature_id is None:
        if forms.count == 0:
            raise Exception("No form features in the design")
        return forms.item(forms.count - 1)

    # Try by name
    feat = forms.itemByName(feature_id)
    if feat:
        return feat

    # Try by index
    try:
        idx = int(feature_id)
        if 0 <= idx < forms.count:
            return forms.item(idx)
    except ValueError:
        pass

    available = [forms.item(i).name for i in range(forms.count)]
    raise Exception(f"Form feature '{feature_id}' not found. Available: {available}")


def _get_tspline_body(form_feature, body_index=0):
    """Get a TSplineBody from a form feature."""
    bodies = form_feature.tSplineBodies
    if bodies.count == 0:
        raise Exception(f"Form feature '{form_feature.name}' has no T-Spline bodies")
    if body_index >= bodies.count:
        raise Exception(f"Body index {body_index} out of range ({bodies.count} bodies)")
    return bodies.item(body_index)


# ── Handlers ─────────────────────────────────────────────────

def handle_form_create(body):
    """Create a T-Spline form feature with a primitive body.

    WARNING: form features require a parametric design. Calling this on
    a direct (non-parametric) design fails with InternalValidationError
    and may corrupt design state. We assert parametric up-front and also
    capture the design type before/after to detect silent flips.
    """
    assert_parametric("form_create")
    type_before = current_design_type()
    root = get_root()
    form_type = body.get("type", "box")

    # Generate TSM description (all dims in cm for Fusion internal units)
    if form_type == "box":
        lx = body.get("length", 100) / 10.0
        ly = body.get("width", 100) / 10.0
        lz = body.get("height", 100) / 10.0
        tsm = _tsm_box(lx, ly, lz)
    elif form_type == "cylinder":
        r = body.get("radius", 50) / 10.0
        h = body.get("height", 100) / 10.0
        radial = body.get("radial_facets", 8)
        tsm = _tsm_cylinder(r, h, radial)
    elif form_type == "sphere":
        r = body.get("radius", 50) / 10.0
        tsm = _tsm_sphere(r)
    elif form_type == "torus":
        major = body.get("major_radius", 50) / 10.0
        minor = body.get("minor_radius", 15) / 10.0
        radial = body.get("radial_facets", 12)
        tubular = body.get("tubular_facets", 8)
        tsm = _tsm_torus(major, minor, radial, tubular)
    elif form_type == "pipe":
        outer = body.get("outer_radius", 50) / 10.0
        inner = body.get("inner_radius", 40) / 10.0
        h = body.get("height", 100) / 10.0
        radial = body.get("radial_facets", 8)
        tsm = _tsm_pipe(outer, inner, h, radial)
    else:
        raise Exception(f"Unknown form type: {form_type}. Use: box, cylinder, sphere, torus, pipe")

    # Write TSM to temp file and create via addByTSMFile
    forms = root.features.formFeatures

    # First try addByTSMFile via temp file (more reliable than description string)
    tmp_path = os.path.join(tempfile.gettempdir(), "_fusion_form_tmp.tsm")
    with open(tmp_path, "w") as f:
        f.write(tsm)

    feat = forms.add()
    if not feat:
        raise Exception("Failed to create form feature. Ensure design is saved and in parametric mode.")

    feat.startEdit()
    ts_body = feat.tSplineBodies.addByTSMFile(tmp_path)
    if not ts_body:
        # Fallback: try description string
        ts_body = feat.tSplineBodies.addByTSMDescription(tsm)
    feat.finishEdit()
    adsk.doEvents()

    try:
        os.remove(tmp_path)
    except OSError:
        pass

    result = {
        "feature_id": feat.name,
        "type": form_type,
        "tspline_body_count": feat.tSplineBodies.count,
    }
    if ts_body:
        result["body_name"] = ts_body.name

    # Detect silent design-type corruption (the bug that ate hours of work)
    type_after = current_design_type()
    if type_after != type_before:
        result["WARNING_design_type_changed"] = (
            f"Design type silently flipped from {type_before} -> {type_after} "
            "during form_create. This is a Fusion API bug. The timeline may "
            "have been destroyed. Direct -> parametric conversion is NOT "
            "supported, so this is unrecoverable in the same document."
        )
    return result


def handle_form_info(body):
    """List form features, or detail a specific form's T-Spline topology."""
    root = get_root()
    feature_id = body.get("feature_id")

    if not feature_id:
        forms = root.features.formFeatures
        result = []
        for i in range(forms.count):
            f = forms.item(i)
            result.append({
                "index": i,
                "name": f.name,
                "tspline_bodies": f.tSplineBodies.count,
            })
        return {"form_features": result, "count": forms.count}

    form_feature = _get_form_feature(root, feature_id)
    ts_bodies = []
    for i in range(form_feature.tSplineBodies.count):
        b = form_feature.tSplineBodies.item(i)
        ts_bodies.append({"index": i, "name": b.name})

    brep_bodies = []
    if form_feature.bodies:
        for i in range(form_feature.bodies.count):
            b = form_feature.bodies.item(i)
            brep_bodies.append({"index": i, "name": b.name})

    return {
        "feature_id": feature_id,
        "name": form_feature.name,
        "tspline_body_count": form_feature.tSplineBodies.count,
        "tspline_bodies": ts_bodies,
        "brep_body_count": len(brep_bodies),
        "brep_bodies": brep_bodies,
    }


def handle_form_export_tsm(body):
    """Export a T-Spline body as TSM text."""
    root = get_root()
    form_feature = _get_form_feature(root, body.get("feature_id"))
    body_index = body.get("body_index", 0)
    ts_body = _get_tspline_body(form_feature, body_index)

    tsm = ts_body.getTSMDescription()
    return {
        "feature_id": form_feature.name,
        "body_name": ts_body.name,
        "tsm": tsm,
    }


def handle_form_import_tsm(body):
    """Import a T-Spline body from TSM text into a form feature.

    See handle_form_create for the parametric-only requirement and the
    silent design-type corruption guard.
    """
    assert_parametric("form_import_tsm")
    type_before = current_design_type()
    root = get_root()
    tsm = body.get("tsm")
    if not tsm:
        raise Exception("tsm parameter is required (TSM format string)")

    feature_id = body.get("feature_id")
    if feature_id:
        form_feature = _get_form_feature(root, feature_id)
    else:
        form_feature = root.features.formFeatures.add()
        if not form_feature:
            raise Exception("Failed to create form feature")

    form_feature.startEdit()
    ts_body = form_feature.tSplineBodies.addByTSMDescription(tsm)
    form_feature.finishEdit()
    adsk.doEvents()

    result = {
        "feature_id": form_feature.name,
        "body_name": ts_body.name if ts_body else None,
        "success": ts_body is not None,
    }
    type_after = current_design_type()
    if type_after != type_before:
        result["WARNING_design_type_changed"] = (
            f"Design type silently flipped from {type_before} -> {type_after}. "
            "Timeline may have been destroyed; this is unrecoverable in the "
            "same document."
        )
    return result


def handle_form_freeze(body):
    """Finish editing a form feature (converts T-Spline to BRep)."""
    root = get_root()
    form_feature = _get_form_feature(root, body.get("feature_id"))
    form_feature.finishEdit()
    adsk.doEvents()

    bodies = []
    if form_feature.bodies:
        bodies = [form_feature.bodies.item(i).name
                  for i in range(form_feature.bodies.count)]
    return {"frozen": True, "body_ids": bodies}


def handle_form_edit_start(body):
    """Enter edit mode on a form feature."""
    root = get_root()
    form_feature = _get_form_feature(root, body.get("feature_id"))
    ok = form_feature.startEdit()
    return {"editing": ok, "feature_id": form_feature.name}


def handle_form_edit_finish(body):
    """Exit edit mode on a form feature."""
    root = get_root()
    form_feature = _get_form_feature(root, body.get("feature_id"))
    ok = form_feature.finishEdit()
    adsk.doEvents()
    return {"finished": ok, "feature_id": form_feature.name}


def handle_form_delete(body):
    """Delete a form feature."""
    root = get_root()
    form_feature = _get_form_feature(root, body.get("feature_id"))
    name = form_feature.name
    ok = form_feature.deleteMe()
    return {"deleted": ok, "feature_id": name}


FORM_ROUTES = {
    "/form_create": handle_form_create,
    "/form_info": handle_form_info,
    "/form_export_tsm": handle_form_export_tsm,
    "/form_import_tsm": handle_form_import_tsm,
    "/form_freeze": handle_form_freeze,
    "/form_edit_start": handle_form_edit_start,
    "/form_edit_finish": handle_form_edit_finish,
    "/form_delete": handle_form_delete,
}
