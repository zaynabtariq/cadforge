"""Mesh workspace handlers for Fusion 360 MCP Bridge.

Exposes Fusion's mesh-body operations: info, face-group segmentation,
primitive fitting, mesh→BRep conversion, mesh reduction. The point is to
let an AI agent reason about an imported mesh in terms of *features*
(face groups, fitted primitives) instead of raw triangle slices.

Endpoints:
  /mesh_list                    — list mesh bodies in active design
  /mesh_info                    — bbox, triangle/vertex counts, volume
  /mesh_diagnose                — introspect API surface (debug)
  /mesh_face_groups             — list face groups on a mesh body
  /mesh_generate_face_groups    — auto-segment mesh into face groups
  /mesh_fit_primitive           — fit plane/cylinder/sphere to face group
  /mesh_convert_to_brep         — convert mesh body to BRep solid
  /mesh_reduce                  — decimate mesh
"""

import traceback

import adsk.core
import adsk.fusion

import bridge_helpers as _bh


# ── helpers ──────────────────────────────────────────────────

def _get_app():
    if not _bh.app:
        raise Exception("Fusion app not initialized")
    return _bh.app


def _get_design():
    app = _get_app()
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        raise Exception("Active product is not a Fusion design")
    return design


def _all_mesh_bodies(design):
    """Walk all components and return (component, mesh_body) pairs."""
    result = []
    root = design.rootComponent
    for mb in root.meshBodies:
        result.append((root, mb))
    for occ in root.allOccurrences:
        for mb in occ.component.meshBodies:
            result.append((occ.component, mb))
    return result


def _find_mesh_body(design, name):
    for comp, mb in _all_mesh_bodies(design):
        if mb.name == name:
            return comp, mb
    raise Exception(f"Mesh body '{name}' not found. Available: "
                    f"{[mb.name for _, mb in _all_mesh_bodies(design)]}")


def _bbox_mm(bb):
    return {
        "min_mm": [bb.minPoint.x * 10, bb.minPoint.y * 10, bb.minPoint.z * 10],
        "max_mm": [bb.maxPoint.x * 10, bb.maxPoint.y * 10, bb.maxPoint.z * 10],
        "size_mm": [
            (bb.maxPoint.x - bb.minPoint.x) * 10,
            (bb.maxPoint.y - bb.minPoint.y) * 10,
            (bb.maxPoint.z - bb.minPoint.z) * 10,
        ],
    }


def _safe_attrs(obj):
    """Return public attribute names that don't blow up on access."""
    out = []
    for name in dir(obj):
        if name.startswith("_"):
            continue
        try:
            v = getattr(obj, name)
            kind = type(v).__name__
            out.append({"name": name, "kind": kind, "callable": callable(v)})
        except Exception as e:
            out.append({"name": name, "error": str(e)})
    return out


# ── handlers ──────────────────────────────────────────────────

def handle_mesh_list(body):
    try:
        design = _get_design()
        rows = []
        for comp, mb in _all_mesh_bodies(design):
            try:
                tris = mb.mesh.triangleCount
            except Exception:
                tris = None
            rows.append({
                "name": mb.name,
                "component": comp.name,
                "triangle_count": tris,
                "is_visible": getattr(mb, "isVisible", None),
            })
        return {"mesh_bodies": rows, "count": len(rows)}
    except Exception as e:
        return {"error": True, "message": str(e), "traceback": traceback.format_exc()}


def handle_mesh_info(body):
    try:
        design = _get_design()
        name = body.get("name")
        if not name:
            raise Exception("'name' is required")
        comp, mb = _find_mesh_body(design, name)

        info = {
            "name": mb.name,
            "component": comp.name,
            "is_visible": getattr(mb, "isVisible", None),
        }
        try:
            info["bbox"] = _bbox_mm(mb.boundingBox)
        except Exception as e:
            info["bbox_error"] = str(e)
        try:
            mesh = mb.mesh  # PolygonMesh / TriangleMesh
            info["triangle_count"] = mesh.triangleCount
            info["node_count"] = mesh.nodeCount
        except Exception as e:
            info["mesh_error"] = str(e)
        try:
            info["face_group_count"] = mb.faceGroups.count
        except Exception as e:
            info["face_group_error"] = str(e)
        try:
            info["volume_mm3"] = mb.volume * 1000  # cm^3 -> mm^3
        except Exception as e:
            info["volume_error"] = str(e)
        try:
            info["area_mm2"] = mb.area * 100  # cm^2 -> mm^2
        except Exception as e:
            info["area_error"] = str(e)
        return info
    except Exception as e:
        return {"error": True, "message": str(e), "traceback": traceback.format_exc()}


def handle_mesh_diagnose(body):
    """Introspect a mesh body's API surface so we know what's actually available."""
    try:
        design = _get_design()
        name = body.get("name")
        if not name:
            raise Exception("'name' is required")
        comp, mb = _find_mesh_body(design, name)

        result: dict = {
            "mesh_body_attrs": _safe_attrs(mb),
        }
        try:
            result["mesh_attrs"] = _safe_attrs(mb.mesh)
        except Exception as e:
            result["mesh_attrs_error"] = str(e)
        try:
            result["mesh_bodies_collection_attrs"] = _safe_attrs(comp.meshBodies)
        except Exception as e:
            result["mesh_bodies_collection_attrs_error"] = str(e)
        try:
            mfg = mb.meshFaceGroups
            result["face_groups_collection_attrs"] = _safe_attrs(mfg)
            result["face_groups_count"] = mfg.count
            if mfg.count > 0:
                result["face_group_0_attrs"] = _safe_attrs(mfg.item(0))
        except Exception as e:
            result["face_groups_error"] = str(e)

        # Also probe features that might be relevant
        try:
            feats = comp.features
            result["mesh_related_features"] = sorted([
                a for a in dir(feats)
                if "mesh" in a.lower() or "convert" in a.lower() or "reduce" in a.lower()
            ])
        except Exception as e:
            result["features_error"] = str(e)

        return result
    except Exception as e:
        return {"error": True, "message": str(e), "traceback": traceback.format_exc()}


def handle_mesh_face_groups(body):
    try:
        design = _get_design()
        name = body.get("name")
        if not name:
            raise Exception("'name' is required")
        comp, mb = _find_mesh_body(design, name)

        groups = []
        try:
            mfg = mb.faceGroups
            for i in range(mfg.count):
                g = mfg.item(i)
                row: dict = {"index": i}
                try:
                    row["id"] = g.id
                except Exception:
                    try:
                        row["temp_id"] = g.tempId
                    except Exception:
                        pass
                try:
                    row["name"] = g.name
                except Exception:
                    pass
                try:
                    row["facet_count"] = g.facetCount
                except Exception:
                    try:
                        row["facet_count"] = len(g.facetIndexes)
                    except Exception:
                        pass
                try:
                    bb = g.boundingBox
                    row["bbox"] = _bbox_mm(bb)
                except Exception:
                    pass
                groups.append(row)
        except Exception as e:
            return {"error": True, "message": f"face groups: {e}",
                    "traceback": traceback.format_exc()}

        return {
            "mesh_body": name,
            "face_group_count": len(groups),
            "face_groups": groups,
        }
    except Exception as e:
        return {"error": True, "message": str(e), "traceback": traceback.format_exc()}


def handle_mesh_generate_face_groups(body):
    """Run Fusion's auto face-group recognition on a mesh body."""
    try:
        design = _get_design()
        name = body.get("name")
        if not name:
            raise Exception("'name' is required")
        comp, mb = _find_mesh_body(design, name)

        feats = comp.features
        col = feats.meshGenerateFaceGroupsFeatures

        # Introspect createInput signature by trying common shapes
        inp = None
        used_signature = None
        if hasattr(col, "createInput"):
            for attempt in ("by_body", "by_collection"):
                try:
                    if attempt == "by_body":
                        inp = col.createInput(mb)
                    elif attempt == "by_collection":
                        coll = adsk.core.ObjectCollection.create()
                        coll.add(mb)
                        inp = col.createInput(coll)
                    used_signature = attempt
                    break
                except Exception:
                    inp = None

        if inp is None:
            # Fallback: introspect createInput's signature info
            return {
                "error": True,
                "message": "createInput signature not detected",
                "available": _safe_attrs(col),
            }

        feat = col.add(inp)
        adsk.doEvents()
        return {
            "success": True,
            "feature_name": feat.name if hasattr(feat, "name") else None,
            "signature_used": used_signature,
            "face_group_count_after": mb.faceGroups.count,
        }
    except Exception as e:
        return {"error": True, "message": str(e), "traceback": traceback.format_exc()}


def handle_mesh_convert_to_brep(body):
    """Convert a mesh body to BRep using meshConvertFeatures."""
    try:
        design = _get_design()
        name = body.get("name")
        if not name:
            raise Exception("'name' is required")
        comp, mb = _find_mesh_body(design, name)

        col = comp.features.meshConvertFeatures
        # Introspect createInput
        inp = None
        used = None
        for attempt in ("by_collection", "by_body"):
            try:
                if attempt == "by_collection":
                    coll = adsk.core.ObjectCollection.create()
                    coll.add(mb)
                    inp = col.createInput(coll)
                elif attempt == "by_body":
                    inp = col.createInput(mb)
                used = attempt
                break
            except Exception:
                inp = None

        if inp is None:
            return {
                "error": True,
                "message": "createInput signature not detected",
                "available": _safe_attrs(col),
            }

        feat = col.add(inp)
        adsk.doEvents()

        new_brep_names = []
        try:
            for i in range(feat.bodies.count):
                new_brep_names.append(feat.bodies.item(i).name)
        except Exception:
            pass

        return {
            "success": True,
            "feature_name": feat.name if hasattr(feat, "name") else None,
            "signature_used": used,
            "brep_bodies": new_brep_names,
        }
    except Exception as e:
        return {"error": True, "message": str(e), "traceback": traceback.format_exc()}


def handle_mesh_fit_primitive(body):
    """Fit a plane / cylinder / sphere to a face group on a mesh body.

    Strategy: probe Fusion's primitive-fit API; if it doesn't exist, sample
    the mesh facet vertices in the face group and do a least-squares fit
    here in Python (no Fusion features needed).
    """
    try:
        design = _get_design()
        name = body.get("name")
        face_group_index = int(body.get("face_group_index", 0))
        prim_kind = body.get("primitive", "plane")  # plane | cylinder | sphere

        if not name:
            raise Exception("'name' is required")
        comp, mb = _find_mesh_body(design, name)

        if face_group_index >= mb.faceGroups.count:
            raise Exception(f"face_group_index {face_group_index} out of range "
                            f"({mb.faceGroups.count} groups)")
        fg = mb.faceGroups.item(face_group_index)

        # Use mb.mesh (PolygonMesh) — it has the flat triangle data fields.
        mesh = mb.mesh
        try:
            nodes_flat = mesh.nodeCoordinatesAsFloat
            indices_flat = mesh.triangleNodeIndices
            tri_groups = mesh.triangleFaceGroupTempIds
        except Exception as e:
            return {"error": True, "message": f"node access: {e}",
                    "traceback": traceback.format_exc()}

        # Try to get the facet indices for this face group; fall back to scanning
        # triangleFaceGroupTempIds for triangles whose group id matches.
        facet_indices = None
        try:
            facet_indices = list(fg.facetIndexes)
        except Exception:
            pass
        if facet_indices is None:
            try:
                fg_id = fg.tempId
            except Exception:
                fg_id = getattr(fg, "id", None)
            if fg_id is None:
                return {"error": True, "message": "could not get face group id"}
            facet_indices = [i for i, gid in enumerate(tri_groups) if gid == fg_id]

        import math
        # Collect unique node ids touched by these facets
        node_ids_set = set()
        for tri_idx in facet_indices:
            for k in range(3):
                node_ids_set.add(indices_flat[tri_idx * 3 + k])

        # Build (N,3) array of points in mm
        pts = []
        for nid in node_ids_set:
            x = nodes_flat[nid * 3] * 10
            y = nodes_flat[nid * 3 + 1] * 10
            z = nodes_flat[nid * 3 + 2] * 10
            pts.append((x, y, z))

        n_pts = len(pts)
        if n_pts < 4:
            raise Exception(f"face group has only {n_pts} points; need >=4")

        # Compute centroid
        cx = sum(p[0] for p in pts) / n_pts
        cy = sum(p[1] for p in pts) / n_pts
        cz = sum(p[2] for p in pts) / n_pts

        result = {
            "mesh_body": name,
            "face_group_index": face_group_index,
            "primitive": prim_kind,
            "n_points_used": n_pts,
            "centroid_mm": [cx, cy, cz],
        }

        if prim_kind == "plane":
            # Plane fit: SVD of centered points -> smallest singular vector = normal
            # Implement without numpy by using power iteration on covariance matrix.
            # Compute 3x3 covariance.
            sxx = syy = szz = sxy = sxz = syz = 0.0
            for x, y, z in pts:
                dx, dy, dz = x - cx, y - cy, z - cz
                sxx += dx * dx
                syy += dy * dy
                szz += dz * dz
                sxy += dx * dy
                sxz += dx * dz
                syz += dy * dz
            cov = [[sxx, sxy, sxz], [sxy, syy, syz], [sxz, syz, szz]]

            # Power iteration to find largest eigenvector, then deflate twice.
            def matvec(M, v):
                return [
                    M[0][0]*v[0] + M[0][1]*v[1] + M[0][2]*v[2],
                    M[1][0]*v[0] + M[1][1]*v[1] + M[1][2]*v[2],
                    M[2][0]*v[0] + M[2][1]*v[1] + M[2][2]*v[2],
                ]
            def norm(v):
                return math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)
            def normalize(v):
                n = norm(v)
                return [c / n for c in v] if n > 0 else v

            def power_iter(M, n_iter=80):
                v = [1.0, 1.0, 1.0]
                for _ in range(n_iter):
                    v = normalize(matvec(M, v))
                lam = sum(matvec(M, v)[i] * v[i] for i in range(3))
                return lam, v

            def deflate(M, lam, v):
                return [
                    [M[i][j] - lam * v[i] * v[j] for j in range(3)]
                    for i in range(3)
                ]

            lam1, v1 = power_iter(cov)
            cov2 = deflate(cov, lam1, v1)
            lam2, v2 = power_iter(cov2)
            cov3 = deflate(cov2, lam2, v2)
            lam3, v3 = power_iter(cov3)

            # Smallest eigenvalue's eigenvector is the plane normal
            eig_pairs = sorted([(lam1, v1), (lam2, v2), (lam3, v3)], key=lambda x: x[0])
            normal = eig_pairs[0][1]
            # Compute residuals (perpendicular distance from each point to plane)
            d = -(normal[0] * cx + normal[1] * cy + normal[2] * cz)
            sq_err = 0.0
            for p in pts:
                dist = normal[0]*p[0] + normal[1]*p[1] + normal[2]*p[2] + d
                sq_err += dist * dist
            rms = math.sqrt(sq_err / n_pts)
            result["normal"] = normal
            result["d"] = d  # plane: n·p + d = 0
            result["rms_mm"] = rms
            result["eigenvalues"] = [eig_pairs[0][0], eig_pairs[1][0], eig_pairs[2][0]]

        elif prim_kind == "sphere":
            # Algebraic sphere fit: minimize |p - c|^2 - r^2 = 0
            # Linear system: 2cx*x + 2cy*y + 2cz*z + (r^2 - cx^2-cy^2-cz^2) = x^2+y^2+z^2
            # Solve via normal equations.
            # Build A (N,4) and b (N,)
            A = []
            b = []
            for x, y, z in pts:
                A.append([2*x, 2*y, 2*z, 1.0])
                b.append(x*x + y*y + z*z)
            # Solve A^T A x = A^T b for x = [cx, cy, cz, k] where k = r^2 - cx^2 - cy^2 - cz^2
            # Compute 4x4 normal matrix
            N = [[0.0]*4 for _ in range(4)]
            rhs = [0.0]*4
            for i in range(n_pts):
                for j in range(4):
                    rhs[j] += A[i][j] * b[i]
                    for k in range(4):
                        N[j][k] += A[i][j] * A[i][k]
            # Solve 4x4 by Gaussian elimination
            def solve(M, v):
                M = [row[:] for row in M]
                v = v[:]
                n = len(M)
                for i in range(n):
                    pivot = i
                    for r in range(i+1, n):
                        if abs(M[r][i]) > abs(M[pivot][i]):
                            pivot = r
                    M[i], M[pivot] = M[pivot], M[i]
                    v[i], v[pivot] = v[pivot], v[i]
                    if abs(M[i][i]) < 1e-12:
                        return None
                    for r in range(i+1, n):
                        f = M[r][i] / M[i][i]
                        for c in range(i, n):
                            M[r][c] -= f * M[i][c]
                        v[r] -= f * v[i]
                x = [0.0]*n
                for i in reversed(range(n)):
                    s = v[i]
                    for j in range(i+1, n):
                        s -= M[i][j] * x[j]
                    x[i] = s / M[i][i]
                return x
            sol = solve(N, rhs)
            if sol is None:
                raise Exception("sphere fit singular")
            scx, scy, scz, k = sol
            r_sq = k + scx*scx + scy*scy + scz*scz
            if r_sq <= 0:
                raise Exception(f"sphere fit gave negative r^2={r_sq}")
            r = math.sqrt(r_sq)
            sq_err = 0.0
            for x, y, z in pts:
                d = math.sqrt((x-scx)**2 + (y-scy)**2 + (z-scz)**2) - r
                sq_err += d*d
            rms = math.sqrt(sq_err / n_pts)
            result["center_mm"] = [scx, scy, scz]
            result["radius_mm"] = r
            result["rms_mm"] = rms

        elif prim_kind == "cylinder":
            # First fit a plane to get the dominant normal direction (axis perpendicular).
            # Cylinder axis = direction of LARGEST variance (largest eigenvector).
            sxx = syy = szz = sxy = sxz = syz = 0.0
            for x, y, z in pts:
                dx, dy, dz = x - cx, y - cy, z - cz
                sxx += dx * dx
                syy += dy * dy
                szz += dz * dz
                sxy += dx * dy
                sxz += dx * dz
                syz += dy * dz
            cov = [[sxx, sxy, sxz], [sxy, syy, syz], [sxz, syz, szz]]
            def matvec(M, v):
                return [
                    M[0][0]*v[0] + M[0][1]*v[1] + M[0][2]*v[2],
                    M[1][0]*v[0] + M[1][1]*v[1] + M[1][2]*v[2],
                    M[2][0]*v[0] + M[2][1]*v[1] + M[2][2]*v[2],
                ]
            def normalize(v):
                n = math.sqrt(sum(c*c for c in v))
                return [c / n for c in v] if n > 0 else v
            v = [1.0, 1.0, 1.0]
            for _ in range(80):
                v = normalize(matvec(cov, v))
            axis = v
            # Project points onto the plane perpendicular to axis, fit circle
            # in that 2D plane.
            # Build orthonormal basis perpendicular to axis
            ax, ay, az = axis
            # Pick any non-parallel vector
            if abs(ax) < 0.9:
                t = [1.0, 0.0, 0.0]
            else:
                t = [0.0, 1.0, 0.0]
            e1 = [t[0] - ax*(t[0]*ax + t[1]*ay + t[2]*az),
                  t[1] - ay*(t[0]*ax + t[1]*ay + t[2]*az),
                  t[2] - az*(t[0]*ax + t[1]*ay + t[2]*az)]
            e1 = normalize(e1)
            e2 = [ay*e1[2] - az*e1[1], az*e1[0] - ax*e1[2], ax*e1[1] - ay*e1[0]]
            # Project each point to (u, v) in this basis (centered at centroid)
            uv = []
            for x, y, z in pts:
                dx, dy, dz = x - cx, y - cy, z - cz
                u = dx*e1[0] + dy*e1[1] + dz*e1[2]
                w = dx*e2[0] + dy*e2[1] + dz*e2[2]
                uv.append((u, w))
            # Algebraic circle fit in 2D: x^2 + y^2 + Dx + Ey + F = 0
            A = []
            b = []
            for u, w in uv:
                A.append([u, w, 1.0])
                b.append(-(u*u + w*w))
            # 3x3 normal equations
            N = [[0.0]*3 for _ in range(3)]
            rhs = [0.0]*3
            for i in range(len(uv)):
                for j in range(3):
                    rhs[j] += A[i][j] * b[i]
                    for k in range(3):
                        N[j][k] += A[i][j] * A[i][k]
            def solve(M, v):
                M = [row[:] for row in M]
                v = v[:]
                n = len(M)
                for i in range(n):
                    pivot = i
                    for r in range(i+1, n):
                        if abs(M[r][i]) > abs(M[pivot][i]):
                            pivot = r
                    M[i], M[pivot] = M[pivot], M[i]
                    v[i], v[pivot] = v[pivot], v[i]
                    if abs(M[i][i]) < 1e-12:
                        return None
                    for r in range(i+1, n):
                        f = M[r][i] / M[i][i]
                        for c in range(i, n):
                            M[r][c] -= f * M[i][c]
                        v[r] -= f * v[i]
                x = [0.0]*n
                for i in reversed(range(n)):
                    s = v[i]
                    for j in range(i+1, n):
                        s -= M[i][j] * x[j]
                    x[i] = s / M[i][i]
                return x
            sol = solve(N, rhs)
            if sol is None:
                raise Exception("circle fit singular")
            D, E, F = sol
            uc = -D / 2
            wc = -E / 2
            r2 = uc*uc + wc*wc - F
            if r2 <= 0:
                raise Exception(f"circle fit gave negative r^2={r2}")
            r = math.sqrt(r2)
            # Cylinder center in 3D: centroid + uc*e1 + wc*e2
            ccx = cx + uc*e1[0] + wc*e2[0]
            ccy = cy + uc*e1[1] + wc*e2[1]
            ccz = cz + uc*e1[2] + wc*e2[2]
            # RMS
            sq_err = 0.0
            for x, y, z in pts:
                # Distance from point to cylinder axis line through (ccx,ccy,ccz) dir (ax,ay,az)
                dx, dy, dz = x - ccx, y - ccy, z - ccz
                # Project onto axis
                t_proj = dx*ax + dy*ay + dz*az
                # Perpendicular component
                px = dx - t_proj*ax
                py = dy - t_proj*ay
                pz = dz - t_proj*az
                d_perp = math.sqrt(px*px + py*py + pz*pz) - r
                sq_err += d_perp * d_perp
            rms = math.sqrt(sq_err / n_pts)
            result["axis_direction"] = list(axis)
            result["axis_point_mm"] = [ccx, ccy, ccz]
            result["radius_mm"] = r
            result["rms_mm"] = rms

        else:
            raise Exception(f"unknown primitive '{prim_kind}'. Use plane, cylinder, sphere")

        return result
    except Exception as e:
        return {"error": True, "message": str(e), "traceback": traceback.format_exc()}


# ── route table ──────────────────────────────────────────────

MESH_ROUTES = {
    "/mesh_list":                  handle_mesh_list,
    "/mesh_info":                  handle_mesh_info,
    "/mesh_diagnose":              handle_mesh_diagnose,
    "/mesh_face_groups":           handle_mesh_face_groups,
    "/mesh_generate_face_groups":  handle_mesh_generate_face_groups,
    "/mesh_fit_primitive":         handle_mesh_fit_primitive,
    "/mesh_convert_to_brep":       handle_mesh_convert_to_brep,
}
