"""Shared state and utility functions for all Fusion bridge handler modules.

Every handler module imports from here. The `app` global is set once
during add-in startup by calling `set_app()`.
"""

import adsk.core
import adsk.fusion
import adsk.cam

# Shared state — set by FusionMCPBridge.run()
app = None
frame_manager = None
entity_resolver = None
cad_state = None
graph_extractor = None
patch_emitter = None
action_executor = None

PORT = 8080


def set_app(a):
    global app
    app = a


def set_frame_manager(fm):
    global frame_manager
    frame_manager = fm


def set_nav_state(er, cs, ge, pe, ae):
    global entity_resolver, cad_state, graph_extractor, patch_emitter, action_executor
    entity_resolver = er
    cad_state = cs
    graph_extractor = ge
    patch_emitter = pe
    action_executor = ae


# ── Design helpers ───────────────────────────────────────────

def get_design():
    """Get the Fusion design (works from any workspace)."""
    global app
    doc = app.activeDocument
    if not doc:
        raise Exception("No active document")
    design = app.activeProduct
    if design and design.productType == "DesignProductType":
        return design
    for product in doc.products:
        if product.productType == "DesignProductType":
            return product
    raise Exception("No Fusion design found in document")


def get_root():
    """Get the root component."""
    return get_design().rootComponent


def current_design_type():
    """Return 'parametric' or 'direct' for the active design."""
    design = get_design()
    if design.designType == adsk.fusion.DesignTypes.ParametricDesignType:
        return "parametric"
    return "direct"


def assert_parametric(operation_name="this operation"):
    """Raise a clear error if the active design isn't parametric.

    Some Fusion API calls (notably FormFeatures.add and timeline operations)
    require parametric mode. Calling them in direct mode either fails with
    cryptic 'InternalValidationError' / 'this is not a parametric design'
    errors, or — worse — silently corrupts state.
    """
    if current_design_type() != "parametric":
        raise Exception(
            f"{operation_name} requires a parametric design, but the active "
            "design is in direct (non-history) mode. Direct designs have no "
            "timeline. Note: Fusion does NOT support converting direct -> "
            "parametric in the same document; you must start a new document "
            "or use File > Save As Parametric (when available)."
        )


# ── Geometry helpers ─────────────────────────────────────────

def point2d(coords):
    """Create a 2D point from [x, y] in mm, converted to cm for Fusion."""
    return adsk.core.Point3D.create(coords[0] / 10.0, coords[1] / 10.0, 0)


def point3d(coords):
    """Create a 3D point from [x, y, z] in mm, converted to cm for Fusion."""
    return adsk.core.Point3D.create(coords[0] / 10.0, coords[1] / 10.0, coords[2] / 10.0)


def vector3d(coords):
    """Create a 3D vector from [x, y, z]."""
    return adsk.core.Vector3D.create(coords[0], coords[1], coords[2])


# ── Listing helpers (for error messages) ─────────────────────

def _all_body_names(root, component=None):
    """Collect all body names from root + occurrences (or a specific component)."""
    names = []
    if component:
        for b in component.bRepBodies:
            names.append(b.name)
    else:
        for b in root.bRepBodies:
            names.append(b.name)
        for occ in root.allOccurrences:
            for b in occ.component.bRepBodies:
                names.append(b.name)
    return names


def _all_sketch_names(root):
    """Collect all sketch names from root + occurrences."""
    names = []
    for sk in root.sketches:
        names.append(sk.name)
    for occ in root.allOccurrences:
        for sk in occ.component.sketches:
            names.append(sk.name)
    return names


def _all_component_names(root):
    """Collect all component names from occurrences."""
    names = []
    for occ in root.allOccurrences:
        names.append(occ.component.name)
    return names


# ── Lookup helpers ───────────────────────────────────────────

def get_component_by_name(name):
    """Get a component by name (e.g., 'Carcass' or 'Carcass:1')."""
    root = get_root()
    base_name = name.split(":")[0] if ":" in name else name
    for occ in root.allOccurrences:
        if occ.component.name == base_name or occ.name == name:
            return occ.component, occ
    return None, None


def find_component(name):
    """Get a component by name or raise with available component names."""
    comp, occ = get_component_by_name(name)
    if comp:
        return comp, occ
    root = get_root()
    available = _all_component_names(root)
    raise Exception(f"Component '{name}' not found. Available: {available}")


def get_sketch(sketch_id):
    """Get a sketch by name, searching root and all components."""
    root = get_root()
    sketch = root.sketches.itemByName(sketch_id)
    if sketch:
        return sketch
    for occ in root.allOccurrences:
        sketch = occ.component.sketches.itemByName(sketch_id)
        if sketch:
            return sketch
    available = _all_sketch_names(root)
    raise Exception(f"Sketch '{sketch_id}' not found. Available: {available}")


def get_sketch_with_component(sketch_id, component_name=None):
    """Get a sketch, optionally from a specific component."""
    root = get_root()
    if component_name:
        target_component, _ = get_component_by_name(component_name)
        if target_component:
            sketch = target_component.sketches.itemByName(sketch_id)
            if sketch:
                return sketch, target_component
    sketch = root.sketches.itemByName(sketch_id)
    if sketch:
        return sketch, root
    for occ in root.allOccurrences:
        sketch = occ.component.sketches.itemByName(sketch_id)
        if sketch:
            return sketch, occ.component
    available = _all_sketch_names(root)
    raise Exception(f"Sketch '{sketch_id}' not found. Available: {available}")


def find_body(body_name, component_name=None):
    """Find a BRepBody or MeshBody by name, optionally scoped to a component."""
    root = get_root()
    if component_name:
        comp, _ = get_component_by_name(component_name)
        if comp:
            for b in comp.bRepBodies:
                if b.name == body_name:
                    return b
            for mb in comp.meshBodies:
                if mb.name == body_name:
                    return mb
    for b in root.bRepBodies:
        if b.name == body_name:
            return b
    for mb in root.meshBodies:
        if mb.name == body_name:
            return mb
    for occ in root.allOccurrences:
        for b in occ.component.bRepBodies:
            if b.name == body_name:
                return b
        for mb in occ.component.meshBodies:
            if mb.name == body_name:
                return mb
    available = _all_body_names(root)
    raise Exception(f"Body '{body_name}' not found. Available: {available}")


# ── Spatial entity resolution ────────────────────────────────

def _pt_distance_mm(fusion_pt, target_mm):
    """Euclidean distance between a Fusion Point3D (cm) and a target [x,y,z] in mm."""
    dx = fusion_pt.x * 10 - target_mm[0]
    dy = fusion_pt.y * 10 - target_mm[1]
    dz = fusion_pt.z * 10 - target_mm[2]
    return (dx * dx + dy * dy + dz * dz) ** 0.5


def find_nearest_edge(body, point_mm, tolerance_mm=10.0):
    """Find the closest edge on a body to a world-space point (mm).

    Uses pointOnEdge (midpoint) for distance. Returns (edge, distance_mm)
    or (None, inf) if nothing is within tolerance.
    """
    best_edge = None
    best_dist = float("inf")
    for i in range(body.edges.count):
        edge = body.edges.item(i)
        dist = _pt_distance_mm(edge.pointOnEdge, point_mm)
        if dist < best_dist:
            best_dist = dist
            best_edge = edge
    if best_dist <= tolerance_mm:
        return best_edge, best_dist
    return None, float("inf")


def find_nearest_face(body, point_mm, tolerance_mm=10.0):
    """Find the closest face on a body to a world-space point (mm).

    Uses face centroid for distance. Returns (face, distance_mm)
    or (None, inf) if nothing is within tolerance.
    """
    best_face = None
    best_dist = float("inf")
    for i in range(body.faces.count):
        face = body.faces.item(i)
        dist = _pt_distance_mm(face.centroid, point_mm)
        if dist < best_dist:
            best_dist = dist
            best_face = face
    if best_dist <= tolerance_mm:
        return best_face, best_dist
    return None, float("inf")


def parse_edge_ref(edge_str, root_component, tolerance_mm=10.0):
    """Resolve an edge string to a live BRepEdge.

    Supports three formats:
      - "Body1_edge_3"    — index-based lookup (legacy)
      - "Body1@170,0,542" — spatial lookup by nearest midpoint
      - "token:abc123..."  — entityToken lookup via resolver cache

    Returns (edge, body) or raises Exception.
    """
    # Format: token:...
    if edge_str.startswith("token:"):
        token = edge_str[6:]
        for b in root_component.bRepBodies:
            for i in range(b.edges.count):
                e = b.edges.item(i)
                if e.entityToken == token:
                    return e, b
        raise Exception(f"Edge token not found: {token[:20]}...")

    # Format: Body@x,y,z
    if "@" in edge_str:
        body_name, coords_str = edge_str.rsplit("@", 1)
        coords = [float(c) for c in coords_str.split(",")]
        if len(coords) != 3:
            raise Exception(f"Spatial ref needs 3 coords: {edge_str}")
        body = None
        for b in root_component.bRepBodies:
            if b.name == body_name:
                body = b
                break
        if not body:
            available = [b.name for b in root_component.bRepBodies]
            raise Exception(f"Body '{body_name}' not found for spatial ref. Available: {available}")
        edge, dist = find_nearest_edge(body, coords, tolerance_mm)
        if not edge:
            raise Exception(
                f"No edge within {tolerance_mm}mm of ({coords_str}) on '{body_name}' ({body.edges.count} edges)"
            )
        return edge, body

    # Format: Body1_edge_3 (legacy index)
    parts = edge_str.rsplit("_edge_", 1)
    if len(parts) == 2:
        body_name = parts[0]
        try:
            idx = int(parts[1])
        except ValueError:
            raise Exception(f"Invalid edge index: {edge_str}")
        for b in root_component.bRepBodies:
            if b.name == body_name and idx < b.edges.count:
                return b.edges.item(idx), b
        # Check if body exists but edge index is out of range
        for b in root_component.bRepBodies:
            if b.name == body_name:
                raise Exception(f"Edge index {idx} out of range on '{body_name}' ({b.edges.count} edges)")
        available = [b.name for b in root_component.bRepBodies]
        raise Exception(f"Body '{body_name}' not found for edge ref. Available: {available}")

    raise Exception(
        f"Unrecognized edge ref format: {edge_str}. "
        "Use Body_edge_N, Body@x,y,z, or token:..."
    )


def _face_normal_vec(face):
    """Get face outward normal as a Vector3D via evaluator parametric range.

    Uses the same parametricRange → getNormalAtParameter pattern used
    in handlers_spatial._face_normal, duplicated here so that
    select_face can live in bridge_helpers with no circular import.
    """
    evaluator = face.evaluator
    param_range = evaluator.parametricRange()
    min_pt = param_range.minPoint
    max_pt = param_range.maxPoint
    mid_u = (min_pt.x + max_pt.x) / 2.0
    mid_v = (min_pt.y + max_pt.y) / 2.0
    mid_param = adsk.core.Point2D.create(mid_u, mid_v)
    (ok, normal) = evaluator.getNormalAtParameter(mid_param)
    L = (normal.x ** 2 + normal.y ** 2 + normal.z ** 2) ** 0.5
    if L > 1e-9:
        normal = adsk.core.Vector3D.create(normal.x / L, normal.y / L, normal.z / L)
    return normal


def _classify_normal_direction(normal, threshold=0.95):
    """Classify a normal vector to +X/-X/+Y/-Y/+Z/-Z or 'angled'.

    Uses dot-product > threshold to snap to the nearest axis.
    Returns a string label.
    """
    axes = [
        ((1, 0, 0), "+X"), ((-1, 0, 0), "-X"),
        ((0, 1, 0), "+Y"), ((0, -1, 0), "-Y"),
        ((0, 0, 1), "+Z"), ((0, 0, -1), "-Z"),
    ]
    for (ax, ay, az), label in axes:
        d = normal.x * ax + normal.y * ay + normal.z * az
        if d > threshold:
            return label
    return "angled"


def _face_area_mm2(face):
    """Get face area in mm^2 (Fusion stores in cm^2)."""
    return face.area * 100.0


def _is_miter_face(normal, threshold=0.95):
    """Return True if the face normal is angled (not axis-aligned).

    A miter face is roughly 45 degrees to at least one world plane.
    """
    return _classify_normal_direction(normal, threshold) == "angled"


def select_face(selector_str, body, root_component=None):
    """Select a face using a semantic selector string.

    Formats:
        "largest:+Z"        -- largest face with +Z normal
        "largest:-Z"        -- largest face with -Z normal
        "area>100000:+Z"    -- face with area > 100000 mm^2 and +Z normal
        "index:7"           -- face by index (legacy, brittle)
        "Body_face_7"       -- face by ID (legacy, brittle)
        "+Z"                -- first face with +Z normal
        "miter"             -- first angled face (45 deg to any plane)

    Args:
        selector_str: The selector string.
        body: A BRepBody to search faces on.
        root_component: Optional root component (unused but reserved).

    Returns:
        BRepFace matching the selector.

    Raises:
        Exception with a detailed list of available faces if no match.
    """
    selector = str(selector_str).strip()

    # ── Collect face info for matching and error messages ──
    face_infos = []
    for i in range(body.faces.count):
        f = body.faces.item(i)
        try:
            normal = _face_normal_vec(f)
            direction = _classify_normal_direction(normal)
            area = _face_area_mm2(f)
        except Exception:
            normal = None
            direction = "unknown"
            area = 0.0
        face_infos.append({
            "face": f,
            "index": i,
            "normal": normal,
            "direction": direction,
            "area": area,
            "face_id": f"{body.name}_face_{i}",
        })

    def _available_summary():
        lines = []
        for fi in face_infos:
            lines.append(
                f"  {fi['face_id']}: direction={fi['direction']}, "
                f"area={round(fi['area'], 2)} mm^2")
        return "\n".join(lines)

    # ── index:N ──
    if selector.startswith("index:"):
        try:
            idx = int(selector.split(":", 1)[1])
        except ValueError:
            raise Exception(
                f"Invalid index selector '{selector}'. Use 'index:N'.")
        if 0 <= idx < body.faces.count:
            return body.faces.item(idx)
        raise Exception(
            f"Face index {idx} out of range (body '{body.name}' has "
            f"{body.faces.count} faces).\nAvailable:\n{_available_summary()}")

    # ── Body_face_N (legacy ID) ──
    if "_face_" in selector:
        parts = selector.rsplit("_face_", 1)
        try:
            idx = int(parts[1])
        except ValueError:
            raise Exception(f"Invalid face ID '{selector}'.")
        if 0 <= idx < body.faces.count:
            return body.faces.item(idx)
        raise Exception(
            f"Face index {idx} out of range on '{body.name}' "
            f"({body.faces.count} faces).\nAvailable:\n{_available_summary()}")

    # ── miter ──
    if selector.lower() == "miter":
        for fi in face_infos:
            if fi["direction"] == "angled":
                return fi["face"]
        raise Exception(
            f"No angled/miter face found on body '{body.name}'.\n"
            f"Available:\n{_available_summary()}")

    # ── largest:DIRECTION ──
    if selector.startswith("largest:"):
        target_dir = selector.split(":", 1)[1].strip()
        candidates = [fi for fi in face_infos if fi["direction"] == target_dir]
        if not candidates:
            raise Exception(
                f"No face with direction '{target_dir}' on body '{body.name}'.\n"
                f"Available:\n{_available_summary()}")
        best = max(candidates, key=lambda fi: fi["area"])
        return best["face"]

    # ── area>THRESHOLD:DIRECTION ──
    if selector.startswith("area>"):
        rest = selector[5:]  # after "area>"
        if ":" not in rest:
            raise Exception(
                f"Invalid area selector '{selector}'. "
                f"Use 'area>THRESHOLD:DIRECTION' (e.g. 'area>100000:+Z').")
        threshold_str, target_dir = rest.split(":", 1)
        try:
            area_threshold = float(threshold_str)
        except ValueError:
            raise Exception(f"Invalid area threshold: '{threshold_str}'")
        target_dir = target_dir.strip()
        candidates = [
            fi for fi in face_infos
            if fi["direction"] == target_dir and fi["area"] > area_threshold
        ]
        if not candidates:
            raise Exception(
                f"No face with direction '{target_dir}' and area > "
                f"{area_threshold} mm^2 on body '{body.name}'.\n"
                f"Available:\n{_available_summary()}")
        best = max(candidates, key=lambda fi: fi["area"])
        return best["face"]

    # ── bare direction: +X/-X/+Y/-Y/+Z/-Z ──
    valid_directions = {"+X", "-X", "+Y", "-Y", "+Z", "-Z"}
    if selector in valid_directions:
        for fi in face_infos:
            if fi["direction"] == selector:
                return fi["face"]
        raise Exception(
            f"No face with direction '{selector}' on body '{body.name}'.\n"
            f"Available:\n{_available_summary()}")

    # ── No match — this is not a selector, return None to let caller
    #    fall back to legacy face ID resolution ──
    return None


def resolve_face_selector(face_id_or_selector, body, root_component=None):
    """Try semantic selector first, then fall back to legacy face ID parsing.

    This is the recommended entry point for handlers that accept a face
    identifier which may be a semantic selector or a legacy face_id/index.

    Returns a BRepFace or raises with available faces listed.
    """
    # Try semantic selector first
    result = select_face(face_id_or_selector, body, root_component)
    if result is not None:
        return result

    # Fall back to legacy: Body_face_N or plain integer index
    selector = str(face_id_or_selector).strip()

    if "_face_" in selector:
        parts = selector.rsplit("_face_", 1)
        try:
            idx = int(parts[1])
        except ValueError:
            raise Exception(f"Invalid face ref: '{selector}'")
        if 0 <= idx < body.faces.count:
            return body.faces.item(idx)
        raise Exception(
            f"Face index {idx} out of range on '{body.name}' "
            f"({body.faces.count} faces)")

    try:
        idx = int(selector)
        if 0 <= idx < body.faces.count:
            return body.faces.item(idx)
        raise Exception(
            f"Face index {idx} out of range on '{body.name}' "
            f"({body.faces.count} faces)")
    except ValueError:
        pass

    raise Exception(
        f"Unrecognized face selector or ID: '{selector}'. "
        f"Use semantic selectors (largest:+Z, miter, +X, etc.) or "
        f"legacy IDs (Body_face_N, index:N).")


def parse_face_ref(face_str, root_component, tolerance_mm=10.0):
    """Resolve a face string to a live BRepFace.

    Supports three formats:
      - "Body1_face_3"    — index-based lookup (legacy)
      - "Body1@170,0,542" — spatial lookup by nearest centroid
      - "token:abc123..."  — entityToken lookup via resolver cache

    Returns (face, body) or raises Exception.
    """
    # Format: token:...
    if face_str.startswith("token:"):
        token = face_str[6:]
        for b in root_component.bRepBodies:
            for i in range(b.faces.count):
                f = b.faces.item(i)
                if f.entityToken == token:
                    return f, b
        raise Exception(f"Face token not found: {token[:20]}...")

    # Format: Body@x,y,z
    if "@" in face_str:
        body_name, coords_str = face_str.rsplit("@", 1)
        coords = [float(c) for c in coords_str.split(",")]
        if len(coords) != 3:
            raise Exception(f"Spatial ref needs 3 coords: {face_str}")
        body = None
        for b in root_component.bRepBodies:
            if b.name == body_name:
                body = b
                break
        if not body:
            available = [b.name for b in root_component.bRepBodies]
            raise Exception(f"Body '{body_name}' not found for spatial ref. Available: {available}")
        face, dist = find_nearest_face(body, coords, tolerance_mm)
        if not face:
            raise Exception(
                f"No face within {tolerance_mm}mm of ({coords_str}) on '{body_name}' ({body.faces.count} faces)"
            )
        return face, body

    # Format: Body1_face_3 (legacy index) or plain int
    body_ref = face_str
    idx = None

    if "_face_" in face_str:
        parts = face_str.rsplit("_face_", 1)
        body_ref = parts[0]
        try:
            idx = int(parts[1])
        except ValueError:
            raise Exception(f"Invalid face index: {face_str}")
    else:
        try:
            idx = int(face_str)
            body_ref = None
        except ValueError:
            raise Exception(
                f"Unrecognized face ref format: {face_str}. "
                "Use Body_face_N, Body@x,y,z, or token:..."
            )

    for b in root_component.bRepBodies:
        if body_ref is None or b.name == body_ref:
            if idx is not None and 0 <= idx < b.faces.count:
                return b.faces.item(idx), b

    # Provide helpful error
    if body_ref:
        for b in root_component.bRepBodies:
            if b.name == body_ref:
                raise Exception(f"Face index {idx} out of range on '{body_ref}' ({b.faces.count} faces)")
        available = [b.name for b in root_component.bRepBodies]
        raise Exception(f"Body '{body_ref}' not found for face ref. Available: {available}")
    raise Exception(f"Face not found: {face_str}")
