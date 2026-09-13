"""CAM Setup / Tools / Post-processing handlers for Fusion 360 MCP Bridge.

Manages the manufacturing infrastructure: setups, stock, WCS, tool
libraries, post-processing, simulation, and machining time.

Every public function has the signature ``handle_*(body: dict) -> dict``
and is registered in CAM_SETUP_ROUTES.

Endpoints (33):
  SETUP MANAGEMENT
    /cam_list_setups       – list all CAM setups
    /cam_create_setup      – create a milling setup (stock, WCS, orientation)
    /cam_edit_setup        – modify an existing setup's parameters
    /cam_delete_setup      – delete a setup
    /cam_duplicate_setup   – clone a setup
    /cam_fix_setup         – fix WCS orientation on a setup
    /cam_get_setup_params  – dump all parameters for discovery/debugging
  STOCK / MODEL / FIXTURE
    /cam_set_model         – set machining model bodies
    /cam_set_fixture       – set fixture bodies (clamp avoidance)
    /cam_derive_body       – import a body from an external .f3d file
    /cam_create_keepout    – create keep-out zone sketches
  TOOL MANAGEMENT
    /cam_list_tools        – list tools from document + libraries
    /cam_create_tool       – create a new tool (and add to local library)
  LIBRARY MANAGEMENT
    /cam_library_list      – list tools in the persistent Local library
    /cam_library_add       – add a tool to the Local library
    /cam_library_remove    – remove a tool from the Local library by index
    /cam_library_import_doc – bulk import document tools into Local library
    /cam_library_export    – export Local library to a JSON file
    /cam_library_import_file – import tools from a JSON file
  OPERATIONS QUERY
    /cam_list_operations   – list all operations in a setup (with summary)
    /cam_select_silhouette – set an operation to use silhouette geometry
  OPERATION MANAGEMENT (setup-level, works on 2D and 3D ops)
    /cam_op_delete         – delete an operation by name
    /cam_op_suppress       – suppress/unsuppress an operation
    /cam_op_rename         – rename an operation
    /cam_op_duplicate      – duplicate an operation with all settings
    /cam_op_reorder        – reorder an operation within its setup
  POST-PROCESSING & SIMULATION
    /cam_generate          – generate toolpaths (one setup or all)
    /cam_post_process      – post-process to G-code
    /cam_simulate          – start simulation
    /cam_cycle_time        – estimate machining cycle time
  WORKSPACE
    /cam_switch            – switch to Manufacturing workspace
    /cam_info              – manufacturing workspace overview
"""

import json
import math
import os
import time
import traceback

import adsk.core
import adsk.fusion
import adsk.cam

try:
    from bridge_helpers import get_design, get_root
except ImportError:
    from .bridge_helpers import get_design, get_root


# ── Helpers ──────────────────────────────────────────────────

def get_cam():
    """Get CAM product — must be in Manufacturing workspace."""
    app = adsk.core.Application.get()
    cam = adsk.cam.CAM.cast(app.activeProduct)
    if cam:
        return cam
    doc = app.activeDocument
    if doc:
        for product in doc.products:
            if product.productType == "CAMProductType":
                return adsk.cam.CAM.cast(product)
    raise Exception("CAM not available. Switch to Manufacturing workspace first.")


def _find_setup(cam, name):
    """Find a setup by name, or return the last one."""
    if name:
        for s in cam.setups:
            if s.name == name:
                return s
        raise Exception(f"Setup not found: {name}")
    if cam.setups.count > 0:
        return cam.setups.item(cam.setups.count - 1)
    raise Exception("No setup available. Create a setup first.")


def _find_op(cam, op_name):
    """Find an operation by name across ALL setups. Returns (op, setup)."""
    for setup in cam.setups:
        for op in setup.allOperations:
            if op.name == op_name:
                return op, setup
    raise Exception(f"Operation not found: {op_name}")


def _find_bodies(root, names):
    """Resolve a list of body names into body objects."""
    bodies = []
    not_found = []
    for name in names:
        found = False
        for b in root.bRepBodies:
            if b.name == name:
                bodies.append(b)
                found = True
                break
        if not found:
            for occ in root.allOccurrences:
                for b in occ.bRepBodies:
                    if b.name == name:
                        bodies.append(b)
                        found = True
                        break
                if found:
                    break
        if not found:
            not_found.append(name)
    return bodies, not_found


def _get_enum_choices(param):
    """Try to extract valid enum choices from a CAM parameter.

    Attempts common enum values and collects those that don't raise.
    Returns a list of valid choice strings, or empty list on failure.
    """
    valid = []
    # Try reading the parameter's current expression to know the type
    try:
        current = param.expression
    except Exception:
        current = None

    # Common enum values seen across CAM parameters
    _COMMON_ENUMS = [
        "'fixed size box'", "'relative size box'", "'from solid'", "'solid'",
        "'bottom 1'", "'bottom 2'", "'bottom 3'", "'bottom 4'",
        "'top 1'", "'top 2'", "'top 3'", "'top 4'",
        "'bottom center'", "'top center'", "'center'",
        "'model orientations'", "'select z axis/plane & x axis'", "'axesZX'",
        "'silhouette'", "'selection'", "'tool containment'",
        "'model bottom'", "'model top'",
        "'climb'", "'conventional'", "'both'",
        "'true'", "'false'",
        "true", "false",
    ]

    for candidate in _COMMON_ENUMS:
        try:
            param.expression = candidate
            valid.append(candidate)
        except Exception:
            pass

    # Restore original value
    if current is not None:
        try:
            param.expression = current
        except Exception:
            pass

    return valid


# ── Setup Management ─────────────────────────────────────────

def _extract_setup_summary(setup):
    """Extract useful summary info from a setup's parameters: stock body,
    model bodies, origin point, Z direction.  Returns a dict."""
    summary = {}
    try:
        params = setup.parameters

        # Stock body name
        stock_mode_p = params.itemByName("job_stockMode")
        if stock_mode_p:
            summary["stock_mode"] = stock_mode_p.expression

        # Stock dimensions (for fixed-size mode)
        for axis in ("X", "Y", "Z"):
            sp = params.itemByName(f"job_stockSize{axis}")
            if sp:
                try:
                    summary[f"stock_size_{axis.lower()}"] = sp.expression
                except Exception:
                    pass

        # Stock solid body
        solid_p = params.itemByName("job_stockSolid")
        if solid_p:
            try:
                cad_val = adsk.cam.CadObjectParameterValue.cast(solid_p.value)
                if cad_val and cad_val.value:
                    bodies = cad_val.value
                    if bodies:
                        summary["stock_body"] = [getattr(b, "name", str(b)) for b in bodies]
            except Exception:
                pass

        # Model bodies
        try:
            models = setup.models
            if models and models.count > 0:
                model_names = []
                for i in range(models.count):
                    obj = models.item(i)
                    model_names.append(getattr(obj, "name", str(obj)))
                summary["model_bodies"] = model_names
        except Exception:
            pass

        # WCS origin point
        origin_p = params.itemByName("wcs_origin_boxPoint")
        if origin_p:
            try:
                summary["origin"] = origin_p.expression
            except Exception:
                pass

        # Z direction / flip
        flip_z_p = params.itemByName("wcs_orientation_flipZ")
        if flip_z_p:
            try:
                summary["flip_z"] = flip_z_p.expression
            except Exception:
                pass

        orient_p = params.itemByName("wcs_orientation_mode")
        if orient_p:
            try:
                summary["orientation_mode"] = orient_p.expression
            except Exception:
                pass

    except Exception:
        pass
    return summary


def handle_cam_list_setups(body):
    cam = get_cam()
    setups = []
    for setup in cam.setups:
        info = {
            "name": setup.name,
            "operation_count": setup.allOperations.count,
        }
        try:
            info["setup_type"] = str(setup.operationType)
        except Exception:
            info["setup_type"] = "unknown"
        try:
            info["is_valid"] = setup.isValid
        except Exception:
            pass

        # Always include summary info (stock, model, origin, Z)
        info["summary"] = _extract_setup_summary(setup)

        if body.get("show_params"):
            param_list = []
            try:
                for param in setup.parameters:
                    param_list.append({
                        "name": param.name,
                        "expression": param.expression
                        if hasattr(param, "expression")
                        else str(param.value),
                    })
            except Exception:
                pass
            info["parameters"] = param_list
        setups.append(info)
    return {"setups": setups, "count": len(setups)}


_ORIGIN_MAP = {
    "bottom-corner":  "'bottom 1'",
    "bottom corner":  "'bottom 1'",
    "top-corner":     "'top 1'",
    "top corner":     "'top 1'",
    "bottom-center":  "'bottom center'",
    "bottom center":  "'bottom center'",
    "top-center":     "'top center'",
    "top center":     "'top center'",
    "center":         "'center'",
    # legacy aliases
    "corner":         "'bottom 1'",
}


def _apply_setup_config(setup, body, changes):
    """Shared logic for configuring a setup (used by both create and edit)."""
    root = get_root()
    params = setup.parameters

    # ── Raw param overrides ──
    param_updates = body.get("params", {})
    for param_name, expression in param_updates.items():
        p = params.itemByName(param_name)
        if p:
            try:
                p.expression = str(expression)
                changes.append(f"{param_name} = {expression}")
            except RuntimeError as e:
                err_msg = str(e)
                if "Invalid enumeration value" in err_msg or "invalid" in err_msg.lower():
                    # Try to extract valid choices from the parameter
                    valid_choices = _get_enum_choices(p)
                    if valid_choices:
                        changes.append(
                            f"{param_name}: invalid value '{expression}'. "
                            f"Valid choices: {valid_choices}")
                    else:
                        changes.append(
                            f"{param_name}: invalid value '{expression}'. Error: {err_msg}")
                else:
                    changes.append(f"{param_name} error: {err_msg}")
        else:
            changes.append(f"Parameter not found: {param_name}")

    # ── Model bodies ──
    model_names = body.get("model")
    if model_names:
        if isinstance(model_names, str):
            model_names = [n.strip() for n in model_names.split(",")]
        model_bodies, not_found = _find_bodies(root, model_names)
        if model_bodies:
            coll = adsk.core.ObjectCollection.create()
            for b in model_bodies:
                coll.add(b)
            setup.models = coll
            changes.append(f"Model: {[b.name for b in model_bodies]}")
        else:
            changes.append(f"Model bodies not found: {not_found}")

    # ── Stock body ──
    stock_body_name = body.get("stock_body")
    if stock_body_name:
        stock_bodies, not_found = _find_bodies(root, [stock_body_name])
        if stock_bodies:
            mode_p = params.itemByName("job_stockMode")
            if mode_p:
                try:
                    mode_p.expression = "'solid'"
                except Exception:
                    pass
            solid_p = params.itemByName("job_stockSolid")
            if solid_p:
                cad_val = adsk.cam.CadObjectParameterValue.cast(solid_p.value)
                if cad_val:
                    cad_val.value = [stock_bodies[0]]
                    changes.append(f"Stock body: {stock_body_name}")
        else:
            changes.append(f"Stock body not found: {stock_body_name}")

    # ── Stock mode: fixed ──
    stock_mode = body.get("stock_mode")
    if stock_mode == "fixed":
        p = params.itemByName("job_stockMode")
        if p:
            p.expression = "'fixed size box'"
            changes.append("Stock mode: fixed size box")
        for axis, dim_key in [("X", "stock_x"), ("Y", "stock_y"), ("Z", "stock_z")]:
            val = body.get(dim_key)
            if val:
                sp = params.itemByName(f"job_stockSize{axis}")
                if sp:
                    sp.expression = f"{val} mm"
                    changes.append(f"Stock {axis}: {val}mm")
    elif stock_mode == "relative":
        p = params.itemByName("job_stockMode")
        if p:
            p.expression = "'relative size box'"
            changes.append("Stock mode: relative")
        offset = body.get("stock_offset")
        if offset is not None:
            p = params.itemByName("job_stockOffsetSides")
            if p:
                p.expression = f"{offset} mm"
                changes.append(f"Stock side offset: {offset}mm")
        top = body.get("stock_top")
        if top is not None:
            p = params.itemByName("job_stockOffsetTop")
            if p:
                p.expression = f"{top} mm"
                changes.append(f"Stock top offset: {top}mm")

    # ── WCS origin point ──
    origin = body.get("origin")
    if origin:
        bp = params.itemByName("wcs_origin_boxPoint")
        if bp:
            expr = _ORIGIN_MAP.get(origin, f"'{origin}'")
            try:
                bp.expression = expr
                changes.append(f"Origin: {origin}")
            except RuntimeError as e:
                err_msg = str(e)
                if "Invalid enumeration value" in err_msg or "invalid" in err_msg.lower():
                    valid = _get_enum_choices(bp)
                    if valid:
                        changes.append(
                            f"Origin: invalid value '{origin}'. "
                            f"Valid choices: {valid}")
                    else:
                        changes.append(f"Origin error: {e}")
                else:
                    changes.append(f"Origin error: {e}")
            except Exception as e:
                changes.append(f"Origin error: {e}")

    # ── WCS axis from faces/edges ──
    z_face_name = body.get("z_face")
    x_edge_name = body.get("x_edge")
    if z_face_name or x_edge_name:
        # Switch to axesZX mode for manual axis selection
        mode_p = params.itemByName("wcs_orientation_mode")
        if mode_p:
            try:
                mode_p.expression = "'axesZX'"
                changes.append("WCS orientation: axesZX (manual)")
            except Exception as e:
                changes.append(f"WCS mode error: {e}")

    if z_face_name:
        z_p = params.itemByName("wcs_orientation_axisZ")
        if z_p:
            from bridge_helpers import parse_face_ref, parse_edge_ref
            entity = None
            try:
                entity = parse_face_ref(z_face_name, root)
            except Exception:
                try:
                    entity = parse_edge_ref(z_face_name, root)
                except Exception:
                    pass
            if entity:
                cad_val = adsk.cam.CadObjectParameterValue.cast(z_p.value)
                if cad_val:
                    cad_val.value = [entity]
                    changes.append(f"Z axis: {z_face_name}")
            else:
                changes.append(f"Z axis entity not found: {z_face_name}")

    if x_edge_name:
        x_p = params.itemByName("wcs_orientation_axisX")
        if x_p:
            from bridge_helpers import parse_face_ref, parse_edge_ref
            entity = None
            try:
                entity = parse_edge_ref(x_edge_name, root)
            except Exception:
                try:
                    entity = parse_face_ref(x_edge_name, root)
                except Exception:
                    pass
            if entity:
                cad_val = adsk.cam.CadObjectParameterValue.cast(x_p.value)
                if cad_val:
                    cad_val.value = [entity]
                    changes.append(f"X axis: {x_edge_name}")
            else:
                changes.append(f"X axis entity not found: {x_edge_name}")

    # ── Flip Z ──
    flip_z = body.get("flip_z")
    flip = body.get("flip")  # shortcut: sets origin=top-corner + flip_z=true
    if flip:
        flip_z = True
        if not origin:
            bp = params.itemByName("wcs_origin_boxPoint")
            if bp:
                try:
                    bp.expression = _ORIGIN_MAP["top-corner"]
                    changes.append("Origin: top-corner (flip)")
                except Exception:
                    pass

    if flip_z is not None:
        p = params.itemByName("wcs_orientation_flipZ")
        if p:
            p.expression = "true" if flip_z else "false"
            changes.append(f"Flip Z: {flip_z}")


def handle_cam_create_setup(body):
    cam = get_cam()
    name = body.get("name", "Setup")

    setup_input = cam.setups.createInput(
        adsk.cam.OperationTypes.MillingOperation
    )
    setup = cam.setups.add(setup_input)
    setup.name = name

    changes = []
    try:
        _apply_setup_config(setup, body, changes)
    except Exception as e:
        changes.append(f"Error: {str(e)}")

    return {
        "setup_id": setup.name,
        "name": setup.name,
        "changes": changes,
    }


def handle_cam_edit_setup(body):
    cam = get_cam()
    setup = _find_setup(cam, body.get("setup"))
    changes = []

    try:
        _apply_setup_config(setup, body, changes)
    except Exception as e:
        changes.append(f"Error: {str(e)}")

    return {"success": True, "setup": setup.name, "changes": changes}


def handle_cam_delete_setup(body):
    cam = get_cam()
    setup_name = body.get("setup")
    if not setup_name:
        raise Exception("setup name is required")
    for s in cam.setups:
        if s.name == setup_name:
            s.deleteMe()
            return {"success": True, "deleted": setup_name}
    raise Exception(f"Setup not found: {setup_name}")


def handle_cam_duplicate_setup(body):
    cam = get_cam()
    setup = _find_setup(cam, body.get("setup"))
    new_name = body.get("new_name")

    new_input = cam.setups.createInput(adsk.cam.OperationTypes.MillingOperation)
    new_setup = cam.setups.add(new_input)
    new_setup.name = new_name or f"{setup.name} Copy"

    src_params = setup.parameters
    dst_params = new_setup.parameters
    copied = 0
    for i in range(src_params.count):
        sp = src_params.item(i)
        dp = dst_params.itemByName(sp.name)
        if dp:
            try:
                dp.expression = sp.expression
                copied += 1
            except Exception:
                pass

    return {
        "success": True,
        "original": setup.name,
        "new_setup": new_setup.name,
        "params_copied": copied,
    }


def handle_cam_fix_setup(body):
    """DEPRECATED: use cam_edit_setup with flip_z=true instead.

    This handler now delegates to cam_edit_setup for backward compatibility.
    """
    # Translate fix params into edit params
    edit_body = {"setup": body.get("setup"), "flip_z": True}
    if body.get("stock_offset") is not None:
        edit_body["stock_offset"] = body["stock_offset"]
    if body.get("stock_top") is not None:
        edit_body["stock_top"] = body["stock_top"]

    result = handle_cam_edit_setup(edit_body)
    result["deprecated"] = True
    result["deprecation_notice"] = (
        "cam_fix_setup is deprecated. Use cam_edit_setup with flip_z=true instead. "
        "CLI: fusion-cam-setup edit --setup <name> --flip-z"
    )
    return result


def handle_cam_get_setup_params(body):
    cam = get_cam()
    setup = _find_setup(cam, body.get("setup"))
    filter_prefix = body.get("filter", "")
    param_list = []
    try:
        for param in setup.parameters:
            if filter_prefix and not param.name.startswith(filter_prefix):
                continue
            info = {"name": param.name}
            try:
                info["expression"] = param.expression
            except Exception:
                pass
            try:
                info["value"] = str(param.value)
            except Exception:
                pass
            param_list.append(info)
    except Exception as e:
        return {"error": str(e)}
    return {"setup": setup.name, "parameters": param_list, "count": len(param_list)}


def handle_cam_wcs(body):
    """Query the WCS (Work Coordinate System) for a setup.

    Returns origin in world coords, axis directions, stock point setting,
    and orientation mode.

    Params:
        setup  (optional) – setup name (defaults to last setup)
    """
    cam = get_cam()
    setup = _find_setup(cam, body.get("setup"))
    params = setup.parameters

    result = {"setup": setup.name}

    # Collect all wcs_* parameters with full detail
    wcs_params = {}
    try:
        for param in params:
            if param.name.startswith("wcs_"):
                info = {"name": param.name}
                try:
                    info["expression"] = param.expression
                except Exception:
                    pass
                try:
                    info["value"] = str(param.value)
                except Exception:
                    pass
                wcs_params[param.name] = info
    except Exception as e:
        result["wcs_param_error"] = str(e)

    result["wcs_parameters"] = wcs_params

    # Extract key fields for convenience
    origin_p = params.itemByName("wcs_origin_boxPoint")
    if origin_p:
        try:
            result["origin_point"] = origin_p.expression
        except Exception:
            pass

    mode_p = params.itemByName("wcs_orientation_mode")
    if mode_p:
        try:
            result["orientation_mode"] = mode_p.expression
        except Exception:
            pass

    flip_z_p = params.itemByName("wcs_orientation_flipZ")
    if flip_z_p:
        try:
            result["flip_z"] = flip_z_p.expression
        except Exception:
            pass

    # Try to get the actual WCS origin coordinates from the setup
    try:
        origin_x = params.itemByName("wcs_origin_x")
        origin_y = params.itemByName("wcs_origin_y")
        origin_z = params.itemByName("wcs_origin_z")
        if origin_x and origin_y and origin_z:
            result["origin_world"] = {
                "x": origin_x.expression,
                "y": origin_y.expression,
                "z": origin_z.expression,
            }
    except Exception:
        pass

    return result


# ── Stock / Model / Fixture ──────────────────────────────────

def handle_cam_set_model(body):
    cam = get_cam()
    root = get_root()
    setup = _find_setup(cam, body.get("setup"))
    body_names = body.get("bodies", [])

    bodies, not_found = _find_bodies(root, body_names)
    if not bodies:
        available = [b.name for b in root.bRepBodies]
        raise Exception(f"No bodies found matching {body_names}. Available: {available}")

    coll = adsk.core.ObjectCollection.create()
    for b in bodies:
        coll.add(b)
    try:
        setup.models = coll
    except Exception as e:
        return {"success": False, "error": str(e)}
    return {
        "success": True,
        "bodies": [b.name for b in bodies],
        "message": f"Set {len(bodies)} bodies as machining model",
    }


def handle_cam_set_fixture(body):
    cam = get_cam()
    root = get_root()
    setup = _find_setup(cam, body.get("setup"))
    fixture_names = body.get("fixtures", [])
    if not fixture_names:
        raise Exception("fixtures parameter required — list of body names")

    fixture_bodies, not_found = _find_bodies(root, fixture_names)
    if not fixture_bodies:
        available = [b.name for b in root.bRepBodies]
        raise Exception(f"No fixture bodies found. Available: {available}")

    methods_tried = []

    try:
        if hasattr(setup, "fixture") and setup.fixture is not None:
            existing = setup.fixture
            for b in fixture_bodies:
                existing.add(b)
            methods_tried.append("setup.fixture.add()")
            return {
                "success": True,
                "setup": setup.name,
                "fixtures_set": [b.name for b in fixture_bodies],
                "method": "setup.fixture.add",
            }
    except Exception as e:
        methods_tried.append(f"setup.fixture.add failed: {str(e)[:50]}")

    try:
        coll = adsk.core.ObjectCollection.create()
        for b in fixture_bodies:
            coll.add(b)
        setup.fixture = coll
        methods_tried.append("setup.fixture = collection")
        return {
            "success": True,
            "setup": setup.name,
            "fixtures_set": [b.name for b in fixture_bodies],
            "method": "setup.fixture = ObjectCollection",
        }
    except Exception as e:
        methods_tried.append(f"setup.fixture= failed: {str(e)[:50]}")

    try:
        params = setup.parameters
        fp = params.itemByName("job_fixture")
        if fp:
            pv = adsk.cam.CadObjectParameterValue.cast(fp.value)
            if pv:
                pv.value = fixture_bodies
                methods_tried.append("param_value.value = list")
                return {
                    "success": True,
                    "setup": setup.name,
                    "fixtures_set": [b.name for b in fixture_bodies],
                    "method": "CadObjectParameterValue",
                }
    except Exception as e:
        methods_tried.append(f"param failed: {str(e)[:50]}")

    return {
        "success": False,
        "methods_tried": methods_tried,
        "message": "Could not set fixtures programmatically. Set them manually in the Setup dialog.",
        "bodies_ready": [b.name for b in fixture_bodies],
    }


def handle_cam_derive_body(body):
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    root = design.rootComponent

    source_path = body.get("source_path")
    body_name = body.get("body_name")
    if not source_path:
        raise Exception("source_path is required (path to .f3d file)")
    if not os.path.exists(source_path):
        raise Exception(f"Source file not found: {source_path}")

    current_doc = app.activeDocument
    source_doc = app.documents.open(source_path)
    if not source_doc:
        raise Exception("Failed to open source document")
    adsk.doEvents()
    time.sleep(0.5)
    adsk.doEvents()

    try:
        source_design = adsk.fusion.Design.cast(
            source_doc.products.itemByProductType("Design")
        )
        if not source_design:
            raise Exception("Source document does not contain a Design")
        source_root = source_design.rootComponent

        source_body = None
        for b in source_root.bRepBodies:
            if b.name == body_name:
                source_body = b
                break
        if not source_body:
            for occ in source_root.allOccurrences:
                for b in occ.bRepBodies:
                    if b.name == body_name:
                        source_body = b
                        break
                if source_body:
                    break
        if not source_body:
            available = [b.name for b in source_root.bRepBodies]
            for occ in source_root.allOccurrences:
                for b in occ.bRepBodies:
                    available.append(f"{occ.name}/{b.name}")
            source_doc.close(False)
            raise Exception(f"Body '{body_name}' not found. Available: {available[:20]}")

        current_doc.activate()
        adsk.doEvents()
        target_root = adsk.fusion.Design.cast(app.activeProduct).rootComponent
        copy_body = source_body.copyToComponent(target_root)

        if copy_body:
            derived_name = body.get("new_name", body_name)
            copy_body.name = derived_name
            bbox = copy_body.boundingBox
            dims = {
                "x": round((bbox.maxPoint.x - bbox.minPoint.x) * 10, 2),
                "y": round((bbox.maxPoint.y - bbox.minPoint.y) * 10, 2),
                "z": round((bbox.maxPoint.z - bbox.minPoint.z) * 10, 2),
            }
            result = {
                "success": True,
                "body_name": copy_body.name,
                "dimensions_mm": dims,
            }
        else:
            result = {"success": False, "message": "Failed to copy body"}
        source_doc.close(False)
        return result
    except Exception as e:
        try:
            source_doc.close(False)
        except Exception:
            pass
        raise e


def handle_cam_create_keepout(body):
    root = get_root()
    setup = _find_setup(get_cam(), body.get("setup"))

    corner_size = body.get("corner_size")
    if not corner_size:
        return {"success": False, "message": "Specify corner_size (mm)"}

    try:
        params = setup.parameters
        stock_x = 500
        stock_y = 460
        sx = params.itemByName("job_stockSizeX")
        if sx:
            try:
                stock_x = float(sx.value.value) * 10
            except Exception:
                pass
        sy = params.itemByName("job_stockSizeY")
        if sy:
            try:
                stock_y = float(sy.value.value) * 10
            except Exception:
                pass

        sketch = root.sketches.add(root.xYConstructionPlane)
        sketch.name = "KeepOut_Corners"
        sz = corner_size
        hx, hy = stock_x / 2, stock_y / 2
        corners = [
            (-hx, -hy, -hx + sz, -hy + sz),
            (hx - sz, -hy, hx, -hy + sz),
            (-hx, hy - sz, -hx + sz, hy),
            (hx - sz, hy - sz, hx, hy),
        ]
        created = []
        for i, (x1, y1, x2, y2) in enumerate(corners):
            lines = sketch.sketchCurves.sketchLines
            p1 = adsk.core.Point3D.create(x1 / 10, y1 / 10, 0)
            p2 = adsk.core.Point3D.create(x2 / 10, y1 / 10, 0)
            p3 = adsk.core.Point3D.create(x2 / 10, y2 / 10, 0)
            p4 = adsk.core.Point3D.create(x1 / 10, y2 / 10, 0)
            lines.addByTwoPoints(p1, p2)
            lines.addByTwoPoints(p2, p3)
            lines.addByTwoPoints(p3, p4)
            lines.addByTwoPoints(p4, p1)
            created.append(f"Corner {i+1}: {sz}x{sz}mm")
        return {
            "success": True,
            "sketch_name": sketch.name,
            "zones": created,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Tool Management ──────────────────────────────────────────

def handle_cam_list_tools(body):
    cam = get_cam()
    tool_type_filter = body.get("type")
    tools = []
    sources = []

    # Document tools (from existing operations)
    try:
        doc_tools = set()
        for setup in cam.setups:
            for op in setup.allOperations:
                try:
                    tool = getattr(op, "tool", None) or getattr(op, "activeTool", None)
                    if not tool:
                        continue
                    try:
                        tool_json = json.loads(tool.toJson())
                    except Exception:
                        tool_json = {
                            "description": getattr(tool, "description", "Unknown"),
                            "type": str(getattr(tool, "type", "Unknown")),
                        }
                    geom = tool_json.get("geometry", {})
                    uid = tool_json.get("description", "") + str(geom.get("DC", 0))
                    if uid in doc_tools:
                        continue
                    doc_tools.add(uid)
                    info = {
                        "source": "Document",
                        "from_operation": op.name,
                        "description": tool_json.get("description", ""),
                        "type": tool_json.get("type", ""),
                    }
                    if geom:
                        info["diameter_mm"] = geom.get("DC", 0)
                        info["flute_length_mm"] = geom.get("LCF", 0)
                        info["taper_angle"] = geom.get("TA", 0)
                        info["tip_angle"] = geom.get("SIG", 0)
                    post = tool_json.get("post-process", {})
                    if post:
                        info["tool_number"] = post.get("number", 0)
                    if body.get("full_json"):
                        info["raw_json"] = tool_json
                    if tool_type_filter:
                        combined = (str(info.get("type", "")) + str(info.get("description", ""))).lower()
                        fl = tool_type_filter.lower()
                        if fl in ("chamfer", "v_bit", "v-bit", "vbit"):
                            if "chamfer" not in combined and "v-bit" not in combined and "v bit" not in combined:
                                continue
                        elif fl not in combined:
                            continue
                    tools.append(info)
                except Exception:
                    pass
        sources.append(f"Document: {len(doc_tools)} unique tools")
    except Exception as e:
        sources.append(f"Document: error — {e}")

    # Library tools
    try:
        mgr = adsk.cam.CAMManager.get()
        lib_mgr = mgr.libraryManager
        tool_libs = lib_mgr.toolLibraries
        local_url = tool_libs.urlByLocation(adsk.cam.LibraryLocations.LocalLibraryLocation)
        if local_url:
            child_urls = tool_libs.childAssetURLs(local_url)
            if child_urls:
                for curl in child_urls:
                    try:
                        lib = tool_libs.toolLibraryAtURL(curl)
                        if not lib or lib.count == 0:
                            continue
                        for i in range(min(lib.count, 50)):
                            tool = lib.item(i)
                            if not tool:
                                continue
                            tj = json.loads(tool.toJson())
                            info = {
                                "source": "Local",
                                "index": i,
                                "description": tj.get("description", ""),
                                "type": tj.get("type", ""),
                                "tool_number": tj.get("post-process", {}).get("number", i + 1),
                            }
                            geom = tj.get("geometry", {})
                            if geom:
                                info["diameter_mm"] = geom.get("DC", 0)
                                info["taper_angle"] = geom.get("TA", 0)
                            if tool_type_filter:
                                tstr = str(info.get("type", "")).lower()
                                fl = tool_type_filter.lower()
                                if fl in ("chamfer", "v_bit"):
                                    if "chamfer" not in tstr:
                                        continue
                                elif fl not in tstr:
                                    continue
                            tools.append(info)
                    except Exception:
                        pass
            has_children = False
            for _ in child_urls:
                has_children = True
                break
            if has_children:
                sources.append(f"Local library: {sum(1 for t in tools if t.get('source') == 'Local')} tools")
            else:
                sources.append("Local library: no child libraries found")
    except Exception as e:
        sources.append(f"Libraries: error — {e}")

    return {"sources_checked": sources, "tool_count": len(tools), "tools": tools}


def handle_cam_create_tool(body):
    """Create a new cutting tool and add to the local library."""
    tool_def = _build_tool_def(body)
    tool_type = tool_def["type"]
    diameter = tool_def["geometry"]["DC"]

    try:
        tool = adsk.cam.Tool.createFromJson(json.dumps(tool_def))
        result = {
            "success": True,
            "description": tool_def["description"],
            "type": tool_type,
            "diameter_mm": diameter,
            "tool_number": tool_def["post-process"]["number"],
        }
        if body.get("add_to_library", True):
            try:
                lib_data = _read_local_library_json()
                lib_data["data"].append(json.loads(tool.toJson()))
                _write_local_library_json(lib_data)
                result["added_to_library"] = _LOCAL_LIB_PATH
            except Exception as le:
                result["library_warning"] = str(le)
        return result
    except Exception as e:
        return {"success": False, "error": str(e), "tool_json": tool_def}


# ── Library helpers ──────────────────────────────────────────

_LOCAL_LIB_PATH = os.path.join(
    os.path.expanduser("~"),
    "Library", "Application Support", "Autodesk", "CAM360", "libraries", "Local", "Library.json",
)


def _read_local_library_json():
    """Read the Local library JSON file, returning the parsed data dict."""
    if os.path.exists(_LOCAL_LIB_PATH):
        with open(_LOCAL_LIB_PATH) as f:
            return json.load(f)
    return {"version": 36, "data": []}


def _write_local_library_json(data):
    """Write the Local library JSON file."""
    os.makedirs(os.path.dirname(_LOCAL_LIB_PATH), exist_ok=True)
    with open(_LOCAL_LIB_PATH, "w") as f:
        json.dump(data, f, indent=2)


def _get_api_library_for_read():
    """Get API ToolLibrary for reading (tool lookup). Returns ToolLibrary or None."""
    try:
        mgr = adsk.cam.CAMManager.get()
        tool_libs = mgr.libraryManager.toolLibraries
        local_url = tool_libs.urlByLocation(adsk.cam.LibraryLocations.LocalLibraryLocation)
        if not local_url:
            return None
        child_urls = tool_libs.childAssetURLs(local_url)
        if child_urls:
            for curl in child_urls:
                lib = tool_libs.toolLibraryAtURL(curl)
                if lib:
                    return lib
                break
    except Exception:
        pass
    return None


def _tool_uid(tj):
    """Stable identity key for dedup: description + type + diameter."""
    geom = tj.get("geometry", {})
    return (tj.get("description", ""), tj.get("type", ""), geom.get("DC", 0))


def _build_tool_def(body):
    """Build a tool JSON dict from request body (shared by create_tool and library_add)."""
    tool_type = body.get("type", "flat end mill")
    diameter = body.get("diameter")
    if not diameter:
        raise Exception("diameter (mm) is required")
    tool_def = {
        "description": body.get("description", f"{diameter}mm {tool_type}"),
        "type": tool_type,
        "unit": "millimeters",
        "geometry": {
            "DC": diameter,
            "LCF": body.get("flute_length", diameter * 3),
            "OAL": body.get("overall_length", diameter * 5),
            "NOF": body.get("flutes", 2),
            "SFDM": body.get("shaft_diameter", diameter),
        },
        "post-process": {
            "number": body.get("tool_number", 1),
            "comment": body.get("description", ""),
        },
    }
    if body.get("taper_angle"):
        tool_def["geometry"]["TA"] = body["taper_angle"]
    if body.get("tip_angle"):
        tool_def["geometry"]["SIG"] = body["tip_angle"]
    if body.get("corner_radius"):
        tool_def["geometry"]["RE"] = body["corner_radius"]
    shaft_diameter = body.get("shaft_diameter")
    if shaft_diameter:
        tool_def["shaft"] = {"DC": shaft_diameter}
    feeds = body.get("feeds_speeds", {})
    rpm = feeds.get("spindle_speed", 18000)
    cut_feed = feeds.get("cutting_feedrate", 2000)
    plunge_feed = feeds.get("plunge_feedrate", round(cut_feed / 3))
    ramp_feed = feeds.get("ramp_feedrate", plunge_feed)
    tool_def["start-values"] = {
        "presets": [{
            "name": "Default preset",
            "n": rpm,
            "n_ramp": rpm,
            "v_f": cut_feed,
            "v_f_leadIn": cut_feed,
            "v_f_leadOut": cut_feed,
            "v_f_plunge": plunge_feed,
            "v_f_ramp": ramp_feed,
            "v_f_transition": cut_feed,
            "tool-coolant": "disabled",
            "expressions": {
                "tool_spindleSpeed": f"{rpm} rpm",
                "tool_feedCutting": f"{cut_feed} mmpm",
                "tool_coolant": "'disabled'",
            },
        }]
    }
    return tool_def


# ── Library Management ───────────────────────────────────────

def handle_cam_library_add(body):
    """Add a tool to the persistent Local library.

    Modes:
      - from_operation: copy tool from a named operation in the current document
      - from definition: provide type, diameter, etc. (same as create_tool)
    """
    lib_data = _read_local_library_json()
    from_op = body.get("from_operation")

    if from_op:
        cam = get_cam()
        found = None
        for op in cam.allOperations:
            if op.name == from_op:
                found = op
                break
        if not found:
            raise Exception(f"Operation '{from_op}' not found")
        tool = found.tool
        if not tool:
            raise Exception(f"Operation '{from_op}' has no tool assigned")
        tj = json.loads(tool.toJson())
        lib_data["data"].append(tj)
        _write_local_library_json(lib_data)
        geom = tj.get("geometry", {})
        return {
            "success": True,
            "action": "added_from_operation",
            "operation": from_op,
            "description": tj.get("description", ""),
            "type": tj.get("type", ""),
            "diameter_mm": geom.get("DC", 0),
            "tool_number": tj.get("post-process", {}).get("number", 0),
            "library": _LOCAL_LIB_PATH,
            "library_count": len(lib_data["data"]),
        }

    tool_def = _build_tool_def(body)
    tool = adsk.cam.Tool.createFromJson(json.dumps(tool_def))
    tool_json = json.loads(tool.toJson())
    lib_data["data"].append(tool_json)
    _write_local_library_json(lib_data)
    return {
        "success": True,
        "action": "added_from_definition",
        "description": tool_def["description"],
        "type": tool_def["type"],
        "diameter_mm": body["diameter"],
        "tool_number": tool_def["post-process"]["number"],
        "library": _LOCAL_LIB_PATH,
        "library_count": len(lib_data["data"]),
    }


def handle_cam_library_remove(body):
    """Remove a tool from the Local library by index."""
    index = body.get("index")
    if index is None:
        raise Exception("index is required")
    lib_data = _read_local_library_json()
    tools = lib_data["data"]
    if index < 0 or index >= len(tools):
        raise Exception(f"Index {index} out of range (library has {len(tools)} tools)")
    removed = tools.pop(index)
    _write_local_library_json(lib_data)
    return {
        "success": True,
        "removed_index": index,
        "removed_description": removed.get("description", ""),
        "removed_type": removed.get("type", ""),
        "library_count": len(tools),
    }


def handle_cam_library_import_doc(body):
    """Bulk import unique tools from all document operations into the Local library."""
    cam = get_cam()
    lib_data = _read_local_library_json()

    existing_uids = set()
    for td in lib_data["data"]:
        existing_uids.add(_tool_uid(td))

    added = []
    skipped = []
    for op in cam.allOperations:
        try:
            tool = op.tool
            if not tool:
                continue
            tj = json.loads(tool.toJson())
            uid = _tool_uid(tj)
            if uid in existing_uids:
                skipped.append({"operation": op.name, "description": tj.get("description", ""), "reason": "duplicate"})
                continue
            existing_uids.add(uid)
            lib_data["data"].append(tj)
            geom = tj.get("geometry", {})
            added.append({
                "operation": op.name,
                "description": tj.get("description", ""),
                "type": tj.get("type", ""),
                "diameter_mm": geom.get("DC", 0),
                "tool_number": tj.get("post-process", {}).get("number", 0),
            })
        except Exception:
            pass

    if added:
        _write_local_library_json(lib_data)

    return {
        "success": True,
        "added_count": len(added),
        "skipped_count": len(skipped),
        "added": added,
        "skipped": skipped,
        "library_count": len(lib_data["data"]),
    }


def handle_cam_library_list(body):
    """List tools in the persistent Local library only (not document operations)."""
    lib_data = _read_local_library_json()
    tools = []
    for i, td in enumerate(lib_data["data"]):
        geom = td.get("geometry", {})
        info = {
            "index": i,
            "description": td.get("description", ""),
            "type": td.get("type", ""),
            "diameter_mm": geom.get("DC", 0),
            "flute_length_mm": geom.get("LCF", 0),
            "flutes": geom.get("NOF", 0),
            "overall_length_mm": geom.get("OAL", 0),
            "taper_angle": geom.get("TA", 0),
            "tip_angle": geom.get("SIG", 0),
            "tool_number": td.get("post-process", {}).get("number", 0),
        }
        tools.append(info)
    return {"library": _LOCAL_LIB_PATH, "tool_count": len(tools), "tools": tools}


def handle_cam_library_export(body):
    """Export the Local library to a JSON file."""
    output_path = body.get("output")
    if not output_path:
        raise Exception("output path is required")
    lib_data = _read_local_library_json()
    output_path = os.path.expanduser(output_path)
    with open(output_path, "w") as f:
        json.dump(lib_data, f, indent=2)
    return {"success": True, "path": output_path, "tool_count": len(lib_data["data"])}


def handle_cam_library_import_file(body):
    """Import tools from a JSON file into the Local library."""
    input_path = body.get("input")
    if not input_path:
        raise Exception("input path is required")
    input_path = os.path.expanduser(input_path)
    if not os.path.exists(input_path):
        raise Exception(f"File not found: {input_path}")
    with open(input_path) as f:
        data = json.load(f)

    lib_data = _read_local_library_json()
    existing_uids = set()
    for td in lib_data["data"]:
        existing_uids.add(_tool_uid(td))

    tool_defs = data.get("data", data) if isinstance(data, dict) else data
    added = 0
    skipped = 0
    for td in tool_defs:
        uid = _tool_uid(td)
        if uid in existing_uids:
            skipped += 1
            continue
        lib_data["data"].append(td)
        existing_uids.add(uid)
        added += 1

    if added > 0:
        _write_local_library_json(lib_data)

    return {
        "success": True,
        "added": added,
        "skipped": skipped,
        "library_count": len(lib_data["data"]),
    }


# ── Operations Query ─────────────────────────────────────────

def _extract_op_summary(op):
    """Extract key params (tool, stepdown, stepover, stock-to-leave) for an operation summary."""
    summary = {}
    try:
        params = op.parameters

        # Tool info
        try:
            tool = op.tool
            if tool:
                tj = json.loads(tool.toJson())
                summary["tool_description"] = tj.get("description", "")
                summary["tool_type"] = tj.get("type", "")
                geom = tj.get("geometry", {})
                if geom.get("DC"):
                    summary["tool_diameter_mm"] = geom["DC"]
                post = tj.get("post-process", {})
                if post.get("number"):
                    summary["tool_number"] = post["number"]
        except Exception:
            pass

        # Key machining params
        _SUMMARY_PARAMS = [
            ("maximumStepdown", "stepdown"),
            ("stepover", "stepover"),
            ("maximumStepover", "stepover"),
            ("stockToLeave", "stock_to_leave"),
            ("stockToLeaveAxial", "axial_stock_to_leave"),
            ("stockToLeaveFloor", "floor_stock_to_leave"),
            ("optimalLoad", "optimal_load"),
            ("tolerance", "tolerance"),
            ("useRestMachining", "rest_machining"),
        ]
        for param_name, key in _SUMMARY_PARAMS:
            if key in summary:
                continue  # already set (e.g. stepover from maximumStepover)
            p = params.itemByName(param_name)
            if p:
                try:
                    summary[key] = p.expression
                except Exception:
                    pass
    except Exception:
        pass
    return summary


def handle_cam_list_operations(body):
    cam = get_cam()
    setup_name = body.get("setup")

    if setup_name:
        setup = _find_setup(cam, setup_name)
        setups_to_scan = [setup]
    else:
        setups_to_scan = [cam.setups.item(i) for i in range(cam.setups.count)]

    param_filter = body.get("filter")  # comma-separated substrings

    all_ops = []
    for setup in setups_to_scan:
        for op in setup.allOperations:
            info = {
                "name": op.name,
                "setup": setup.name,
                "has_toolpath": op.hasToolpath,
                "is_suppressed": op.isSuppressed,
            }
            try:
                info["strategy"] = op.strategy
            except Exception:
                pass
            try:
                info["state"] = str(op.operationState)
            except Exception:
                pass

            # Always include summary (#11)
            info["summary"] = _extract_op_summary(op)

            if body.get("show_params"):
                params = []
                skip_prefixes = ("tool_", "holder_")
                op_filter = body.get("operation")

                # Build filter list from comma-separated string (#12)
                filter_terms = []
                if param_filter:
                    filter_terms = [t.strip().lower() for t in param_filter.split(",") if t.strip()]

                try:
                    for param in op.parameters:
                        if not op_filter and param.name.startswith(skip_prefixes):
                            continue
                        # Apply param name filter if provided
                        if filter_terms:
                            pname_lower = param.name.lower()
                            if not any(term in pname_lower for term in filter_terms):
                                continue
                        params.append({
                            "name": param.name,
                            "expression": param.expression
                            if hasattr(param, "expression")
                            else str(param.value),
                        })
                except Exception:
                    pass
                info["parameters"] = params
            all_ops.append(info)

    return {"operations": all_ops, "count": len(all_ops)}


def handle_cam_select_silhouette(body):
    cam = get_cam()
    op_name = body.get("operation")
    if not op_name:
        raise Exception("operation name required")

    op = None
    for setup in cam.setups:
        for o in setup.allOperations:
            if o.name == op_name:
                op = o
                break
        if op:
            break
    if not op:
        raise Exception(f"Operation not found: {op_name}")

    changes = []
    try:
        params = op.parameters
        for pname in ("machiningBoundary", "contour_mode", "boundaryMode"):
            p = params.itemByName(pname)
            if p:
                p.expression = "'silhouette'"
                changes.append(f"Set {pname} to silhouette")
                break
        bm = params.itemByName("bottomHeight_mode")
        if bm:
            bm.expression = "'model bottom'"
            changes.append("Set bottom to model bottom")
    except Exception as e:
        changes.append(f"Error: {e}")

    return {"operation": op_name, "changes": changes}


# ── Post-processing & Simulation ─────────────────────────────

def handle_cam_generate(body):
    cam = get_cam()
    setup_name = body.get("setup")

    if setup_name:
        setup = _find_setup(cam, setup_name)
        future = cam.generateToolpath(setup)
    else:
        future = cam.generateAllToolpaths(True)

    timeout = body.get("timeout", 120)
    start = time.time()
    while not future.isGenerationCompleted:
        if time.time() - start > timeout:
            return {"success": False, "message": "Generation timed out"}
        adsk.doEvents()
        time.sleep(0.2)

    return {
        "success": True,
        "operations_generated": future.numberOfOperations,
    }


def handle_cam_post_process(body):
    cam = get_cam()
    output_path = body.get("output_path")
    if not output_path:
        raise Exception("output_path is required")

    setup = _find_setup(cam, body.get("setup"))
    post_name = body.get("post_processor", "fanuc")

    operations = adsk.core.ObjectCollection.create()
    for op in setup.allOperations:
        if op.hasToolpath:
            operations.add(op)
    if operations.count == 0:
        raise Exception("No operations with toolpaths to post-process")

    post_input = adsk.cam.PostProcessInput.create(output_path, post_name, "", "")
    post_input.isOpenInEditor = body.get("open_editor", False)
    cam.postProcess(setup, post_input)

    return {
        "success": True,
        "output_path": output_path,
        "operations_posted": operations.count,
    }


def handle_cam_simulate(body):
    cam = get_cam()
    setup = _find_setup(cam, body.get("setup"))
    cam.startSimulation(setup)
    return {"success": True, "message": "Simulation started"}


def handle_cam_cycle_time(body):
    cam = get_cam()
    setup = _find_setup(cam, body.get("setup"))

    total_time = 0.0
    op_times = []
    for op in setup.allOperations:
        if op.hasToolpath and not op.isSuppressed:
            try:
                ct = op.machiningTime
                op_times.append({"name": op.name, "time_seconds": round(ct, 1)})
                total_time += ct
            except Exception:
                op_times.append({"name": op.name, "time_seconds": None})

    return {
        "setup": setup.name,
        "total_seconds": round(total_time, 1),
        "total_minutes": round(total_time / 60, 1),
        "operations": op_times,
    }


# ── Workspace ────────────────────────────────────────────────

def handle_cam_switch(body):
    app = adsk.core.Application.get()
    ui = app.userInterface
    ws = ui.workspaces.itemById("CAMEnvironment")
    if ws:
        ws.activate()
        adsk.doEvents()
        return {"success": True, "message": "Switched to Manufacturing workspace"}
    raise Exception("Manufacturing workspace not found")


def handle_cam_info(body):
    try:
        cam = get_cam()
    except Exception:
        return {
            "in_cam_workspace": False,
            "message": "Not in Manufacturing workspace. Use cam_switch first.",
        }

    setups = []
    for s in cam.setups:
        setups.append({
            "name": s.name,
            "operations": s.allOperations.count,
        })

    return {
        "in_cam_workspace": True,
        "setup_count": len(setups),
        "setups": setups,
    }


# ── Operation Management (setup-level) ────────────────────────

def handle_cam_op_delete(body):
    """Delete an operation by name. Searches across all setups."""
    cam = get_cam()
    op_name = body.get("operation")
    if not op_name:
        raise Exception("operation name is required")
    op, setup = _find_op(cam, op_name)
    op.deleteMe()
    return {"success": True, "deleted": op_name, "setup": setup.name}


def handle_cam_op_suppress(body):
    """Suppress or unsuppress an operation. Searches across all setups."""
    cam = get_cam()
    op_name = body.get("operation")
    if not op_name:
        raise Exception("operation name is required")
    op, setup = _find_op(cam, op_name)
    suppress = body.get("suppress", True)
    op.isSuppressed = suppress
    return {"operation": op.name, "suppressed": suppress, "setup": setup.name}


def handle_cam_op_rename(body):
    """Rename an operation. Searches across all setups."""
    cam = get_cam()
    op_name = body.get("operation")
    if not op_name:
        raise Exception("operation name is required")
    new_name = body.get("new_name")
    if not new_name:
        raise Exception("new_name is required")
    op, setup = _find_op(cam, op_name)
    old_name = op.name
    op.name = new_name
    return {"success": True, "old_name": old_name, "new_name": op.name, "setup": setup.name}


def handle_cam_op_duplicate(body):
    """Duplicate an operation with all settings. Searches across all setups."""
    cam = get_cam()
    src_name = body.get("operation")
    if not src_name:
        raise Exception("operation name is required")
    src_op, setup = _find_op(cam, src_name)

    strategy = src_op.strategy
    op_input = setup.operations.createInput(strategy)

    # Copy tool
    src_tool = src_op.tool
    if src_tool:
        op_input.tool = src_tool

    new_op = setup.operations.add(op_input)
    new_op.name = body.get("new_name", f"{src_name} Copy")

    # Copy all parameters
    copied = 0
    skipped = []
    src_params = src_op.parameters
    dst_params = new_op.parameters
    for i in range(src_params.count):
        sp = src_params.item(i)
        dp = dst_params.itemByName(sp.name)
        if dp:
            try:
                dp.expression = sp.expression
                copied += 1
            except Exception:
                skipped.append(sp.name)

    changes = [
        f"Duplicated from '{src_name}'",
        f"Strategy: {strategy}",
        f"Params copied: {copied}",
    ]
    if skipped:
        changes.append(f"Skipped (read-only): {len(skipped)}")

    return {
        "operation": new_op.name,
        "source": src_name,
        "setup": setup.name,
        "changes": changes,
    }


def handle_cam_op_reorder(body):
    """Reorder an operation within its setup.

    Uses position-based reordering: moves the operation to the given
    zero-based position index by repeatedly calling moveUp/moveDown
    on the timeline object.

    Params:
        operation (str) – operation name
        position  (int) – target zero-based index in the setup's operation list
        direction (str) – 'up' or 'down' (alternative: move one step)
    """
    cam = get_cam()
    op_name = body.get("operation")
    if not op_name:
        raise Exception("operation name is required")
    op, setup = _find_op(cam, op_name)

    target_pos = body.get("position")
    direction = body.get("direction")

    if target_pos is not None:
        # Find current position
        ops = setup.allOperations
        current_pos = None
        for i in range(ops.count):
            if ops.item(i).name == op_name:
                current_pos = i
                break
        if current_pos is None:
            raise Exception(f"Could not determine position of '{op_name}'")

        moves = 0
        if target_pos < current_pos:
            # Move up
            for _ in range(current_pos - target_pos):
                try:
                    op.moveUp()
                    moves += 1
                except Exception as e:
                    return {
                        "success": False,
                        "operation": op_name,
                        "error": f"moveUp failed after {moves} moves: {e}",
                        "from_position": current_pos,
                        "target_position": target_pos,
                    }
        elif target_pos > current_pos:
            # Move down
            for _ in range(target_pos - current_pos):
                try:
                    op.moveDown()
                    moves += 1
                except Exception as e:
                    return {
                        "success": False,
                        "operation": op_name,
                        "error": f"moveDown failed after {moves} moves: {e}",
                        "from_position": current_pos,
                        "target_position": target_pos,
                    }

        return {
            "success": True,
            "operation": op_name,
            "from_position": current_pos,
            "to_position": target_pos,
            "moves": moves,
            "setup": setup.name,
        }

    elif direction:
        try:
            if direction == "up":
                op.moveUp()
            else:
                op.moveDown()
            return {"success": True, "operation": op.name, "moved": direction, "setup": setup.name}
        except Exception as e:
            return {"success": False, "operation": op_name, "error": str(e)}

    else:
        raise Exception("Either 'position' (int) or 'direction' ('up'/'down') is required")


# ── Route table ──────────────────────────────────────────────

CAM_SETUP_ROUTES = {
    # Setup management
    "/cam_list_setups": handle_cam_list_setups,
    "/cam_create_setup": handle_cam_create_setup,
    "/cam_edit_setup": handle_cam_edit_setup,
    "/cam_delete_setup": handle_cam_delete_setup,
    "/cam_duplicate_setup": handle_cam_duplicate_setup,
    "/cam_fix_setup": handle_cam_fix_setup,
    "/cam_get_setup_params": handle_cam_get_setup_params,
    "/cam_wcs": handle_cam_wcs,
    # Stock / Model / Fixture
    "/cam_set_model": handle_cam_set_model,
    "/cam_set_fixture": handle_cam_set_fixture,
    "/cam_derive_body": handle_cam_derive_body,
    "/cam_create_keepout": handle_cam_create_keepout,
    # Tool management
    "/cam_list_tools": handle_cam_list_tools,
    "/cam_create_tool": handle_cam_create_tool,
    # Library management
    "/cam_library_list": handle_cam_library_list,
    "/cam_library_add": handle_cam_library_add,
    "/cam_library_remove": handle_cam_library_remove,
    "/cam_library_import_doc": handle_cam_library_import_doc,
    "/cam_library_export": handle_cam_library_export,
    "/cam_library_import_file": handle_cam_library_import_file,
    # Operations query
    "/cam_list_operations": handle_cam_list_operations,
    "/cam_select_silhouette": handle_cam_select_silhouette,
    # Operation management (setup-level, works on 2D and 3D ops)
    "/cam_op_delete": handle_cam_op_delete,
    "/cam_op_suppress": handle_cam_op_suppress,
    "/cam_op_rename": handle_cam_op_rename,
    "/cam_op_duplicate": handle_cam_op_duplicate,
    "/cam_op_reorder": handle_cam_op_reorder,
    # Post-processing & simulation
    "/cam_generate": handle_cam_generate,
    "/cam_post_process": handle_cam_post_process,
    "/cam_simulate": handle_cam_simulate,
    "/cam_cycle_time": handle_cam_cycle_time,
    # Workspace
    "/cam_switch": handle_cam_switch,
    "/cam_info": handle_cam_info,
}
