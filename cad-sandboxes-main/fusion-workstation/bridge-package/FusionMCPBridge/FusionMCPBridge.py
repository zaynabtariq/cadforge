"""
Fusion 360 MCP Bridge Add-in — slim orchestrator.

Delegates handlers to domain modules:
  - handlers_sketch        (complete sketch domain — 38 endpoints)
  - handlers_solid         (features, bodies, transforms)
  - handlers_construction  (planes, axes, points, measurements)
  - handlers_camera        (viewport, screenshots, export)
  - handlers_nav           (STATE / PATCH / LOCAL_GRAPH / frames)
  - handlers_timeline      (parametric timeline)
  - handlers_assembly      (components, joints, hierarchy)
  - handlers_cam_setup     (CAM setups, tools, post-processing)
  - handlers_cam_2d        (2D/2.5D milling operations)
  - handlers_cam_3d        (3D surface machining operations)
  - handlers_data          (Data Panel browsing, document management)
  - handlers_spatial       (spatial reasoning, face maps, transform preview)

The HTTP server, custom-event thread marshaling, and lifecycle (run/stop)
live here.  Individual handler logic lives in the domain modules.
"""

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import adsk.core
import adsk.fusion
import adsk.cam
import threading
import json
import traceback
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

_LOGFILE = os.path.join(_THIS_DIR, "bridge_error.log")

def _log(msg):
    with open(_LOGFILE, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

_log(f"Module load starting. sys.path[0]={sys.path[0] if sys.path else 'empty'}")
_log(f"__file__={__file__}")
_log(f"cwd={os.getcwd()}")

# Force-reload all bridge modules so stop/start picks up file changes
import importlib as _il
for _mod_name in [k for k in sys.modules if k.startswith(("bridge_helpers", "handlers_", "entity_resolver",
                                                            "frame_manager", "cad_state", "graph_extractor",
                                                            "patch_emitter", "action_executor", "_legacy_handlers"))]:
    try:
        _il.reload(sys.modules[_mod_name])
        _log(f"  reloaded cached module: {_mod_name}")
    except Exception:
        del sys.modules[_mod_name]
        _log(f"  purged stale module: {_mod_name}")

# ── Shared helpers ────────────────────────────────────────────
try:
    from bridge_helpers import set_app, set_frame_manager, set_nav_state
    import bridge_helpers as _bh
    _log("bridge_helpers: OK")
except Exception as e:
    _log(f"bridge_helpers FAIL: {e}\n{traceback.format_exc()}")
    raise

# ── Domain handler modules ────────────────────────────────────
try:
    from handlers_sketch import SKETCH_ROUTES
    _log(f"handlers_sketch: OK ({len(SKETCH_ROUTES)} routes)")
except Exception as e:
    _log(f"handlers_sketch FAIL: {e}\n{traceback.format_exc()}")
    raise

try:
    from handlers_solid import SOLID_ROUTES
    _log(f"handlers_solid: OK ({len(SOLID_ROUTES)} routes)")
except Exception as e:
    _log(f"handlers_solid FAIL: {e}\n{traceback.format_exc()}")
    raise

try:
    from handlers_construction import CONSTRUCTION_ROUTES
    _log(f"handlers_construction: OK ({len(CONSTRUCTION_ROUTES)} routes)")
except Exception as e:
    _log(f"handlers_construction FAIL: {e}\n{traceback.format_exc()}")
    raise

try:
    from handlers_camera import CAMERA_ROUTES
    _log(f"handlers_camera: OK ({len(CAMERA_ROUTES)} routes)")
except Exception as e:
    _log(f"handlers_camera FAIL: {e}\n{traceback.format_exc()}")
    raise

try:
    from handlers_nav import NAV_ROUTES
    _log(f"handlers_nav: OK ({len(NAV_ROUTES)} routes)")
except Exception as e:
    _log(f"handlers_nav FAIL: {e}\n{traceback.format_exc()}")
    raise

try:
    from handlers_timeline import TIMELINE_ROUTES
    _log(f"handlers_timeline: OK ({len(TIMELINE_ROUTES)} routes)")
except Exception as e:
    _log(f"handlers_timeline FAIL: {e}\n{traceback.format_exc()}")
    raise

try:
    from handlers_assembly import ASSEMBLY_ROUTES
    _log(f"handlers_assembly: OK ({len(ASSEMBLY_ROUTES)} routes)")
except Exception as e:
    _log(f"handlers_assembly FAIL: {e}\n{traceback.format_exc()}")
    raise

try:
    from handlers_cam_setup import CAM_SETUP_ROUTES
    _log(f"handlers_cam_setup: OK ({len(CAM_SETUP_ROUTES)} routes)")
except Exception as e:
    _log(f"handlers_cam_setup FAIL: {e}\n{traceback.format_exc()}")
    raise

try:
    from handlers_cam_2d import CAM_2D_ROUTES
    _log(f"handlers_cam_2d: OK ({len(CAM_2D_ROUTES)} routes)")
except Exception as e:
    _log(f"handlers_cam_2d FAIL: {e}\n{traceback.format_exc()}")
    raise

try:
    from handlers_cam_3d import CAM_3D_ROUTES
    _log(f"handlers_cam_3d: OK ({len(CAM_3D_ROUTES)} routes)")
except Exception as e:
    _log(f"handlers_cam_3d FAIL: {e}\n{traceback.format_exc()}")
    raise

try:
    from handlers_data import DATA_ROUTES
    _log(f"handlers_data: OK ({len(DATA_ROUTES)} routes)")
except Exception as e:
    _log(f"handlers_data FAIL: {e}\n{traceback.format_exc()}")
    raise

try:
    from handlers_spatial import SPATIAL_ROUTES
    _log(f"handlers_spatial: OK ({len(SPATIAL_ROUTES)} routes)")
except Exception as e:
    _log(f"handlers_spatial FAIL: {e}\n{traceback.format_exc()}")
    raise

try:
    from handlers_mesh import MESH_ROUTES
    _log(f"handlers_mesh: OK ({len(MESH_ROUTES)} routes)")
except Exception as e:
    _log(f"handlers_mesh FAIL: {e}\n{traceback.format_exc()}")
    raise

try:
    from handlers_form import FORM_ROUTES
    _log(f"handlers_form: OK ({len(FORM_ROUTES)} routes)")
except Exception as e:
    _log(f"handlers_form FAIL: {e}\n{traceback.format_exc()}")
    raise

# Frame manager + nav state modules (needed for run() initialization)
try:
    from frame_manager import FrameManager
    from entity_resolver import EntityResolver
    from cad_state import CADState
    from graph_extractor import GraphExtractor
    from patch_emitter import PatchEmitter
    from action_executor import ActionExecutor
    _log("nav core modules: OK")
except Exception as e:
    _log(f"nav core FAIL: {e}\n{traceback.format_exc()}")
    raise

# Legacy handlers — everything not yet split into domain modules
try:
    import _legacy_handlers as _lh
    _log("_legacy_handlers: OK")
except Exception as e:
    _log(f"_legacy_handlers FAIL: {e}\n{traceback.format_exc()}")
    raise

_log("All imports done")

# ── Globals ───────────────────────────────────────────────────
app = None
ui = None
server = None
server_thread = None
custom_event = None
custom_event_handler = None
PORT = 8080

# The VM transport owns per-request state; only this event touches Fusion.
import collections
import queue
from vm_transport import Dispatcher, BoundedServer, Handler, make_logger
dispatcher = None
event_queue = queue.Queue()
event_stop = threading.Event()

def _queue_event(request_id):
    event_queue.put_nowait(request_id)
    return True

def _event_pump():
    # Create this worker directly from Fusion's main thread. HTTP workers
    # never call the Autodesk API (including fireCustomEvent) themselves.
    while not event_stop.is_set():
        try:
            request_id = event_queue.get(timeout=0.25)
        except queue.Empty:
            continue
        try:
            app.fireCustomEvent("FusionMCPCommandEvent", json.dumps({"request_id":request_id}))
        except Exception as exc:
            _log("Custom event dispatch failed: " + str(exc))

class CommandEventHandler(adsk.core.CustomEventHandler):
    def notify(self, args):
        dispatcher.execute(json.loads(args.additionalInfo)["request_id"])

def _readiness(body):
    return {"ready": True, "version": app.version,
            "document_count": app.documents.count,
            "active_document": app.activeDocument.name if app.activeDocument else None}


# ── Master route table ────────────────────────────────────────

ROUTES = {}

_HANDLER_MODULES = {
    "handlers_sketch":       ("SKETCH_ROUTES",),
    "handlers_solid":        ("SOLID_ROUTES",),
    "handlers_construction": ("CONSTRUCTION_ROUTES",),
    "handlers_camera":       ("CAMERA_ROUTES",),
    "handlers_nav":          ("NAV_ROUTES",),
    "handlers_timeline":     ("TIMELINE_ROUTES",),
    "handlers_assembly":     ("ASSEMBLY_ROUTES",),
    "handlers_cam_setup":    ("CAM_SETUP_ROUTES",),
    "handlers_cam_2d":       ("CAM_2D_ROUTES",),
    "handlers_cam_3d":       ("CAM_3D_ROUTES",),
    "handlers_data":         ("DATA_ROUTES",),
    "handlers_spatial":      ("SPATIAL_ROUTES",),
    "handlers_mesh":         ("MESH_ROUTES",),
    "handlers_form":         ("FORM_ROUTES",),
}

_SUPPORT_MODULES = [
    "bridge_helpers", "entity_resolver", "frame_manager",
    "cad_state", "graph_extractor", "patch_emitter",
    "action_executor", "spatial_math", "_legacy_handlers",
]

def _build_routes():
    """(Re)build the master route table from all handler modules."""
    ROUTES.clear()

    for mod_name, route_names in _HANDLER_MODULES.items():
        mod = sys.modules.get(mod_name)
        if mod:
            for rn in route_names:
                ROUTES.update(getattr(mod, rn, {}))

    # Legacy backward-compat aliases
    if "handlers_timeline" in sys.modules:
        tr = getattr(sys.modules["handlers_timeline"], "TIMELINE_ROUTES", {})
        for old, new in [("/undo", "/timeline_undo"), ("/redo", "/timeline_redo"),
                         ("/get_timeline", "/timeline_list"),
                         ("/get_feature_parameters", "/timeline_feature_params"),
                         ("/edit_feature_parameter", "/timeline_edit_param")]:
            if new in tr:
                ROUTES[old] = tr[new]

    if "handlers_cam_2d" in sys.modules:
        c2 = getattr(sys.modules["handlers_cam_2d"], "CAM_2D_ROUTES", {})
        for old, new in [("/cam_create_2d_contour", "/cam_2d_contour"),
                         ("/cam_create_2d_pocket", "/cam_2d_pocket"),
                         ("/cam_create_engrave", "/cam_2d_engrave"),
                         ("/cam_create_trace", "/cam_2d_trace"),
                         ("/cam_create_face", "/cam_2d_face"),
                         ("/cam_create_contour_advanced", "/cam_2d_contour_advanced"),
                         ("/cam_create_miter_clearing", "/cam_2d_miter_clearing")]:
            if new in c2:
                ROUTES[old] = c2[new]

    if "handlers_cam_setup" in sys.modules:
        cs = getattr(sys.modules["handlers_cam_setup"], "CAM_SETUP_ROUTES", {})
        if "/cam_generate" in cs:
            ROUTES["/cam_generate_all"] = cs["/cam_generate"]

    ROUTES.update({
        "/ping": _lh.handle_ping,
        "/info": _lh.handle_info,
        "/new_document": _lh.handle_new_document,
        "/open_document": _lh.handle_open_document,
        "/save": _lh.handle_save,
        "/get_all_parts": _lh.handle_get_all_parts,
        "/create_parameter": _lh.handle_create_parameter,
        "/modify_parameter": _lh.handle_modify_parameter,
        "/list_parameters": _lh.handle_list_parameters,
        "/list_all_parameters": _lh.handle_list_all_parameters,
        "/apply_appearance": _lh.handle_apply_appearance,
        "/list_appearances": _lh.handle_list_appearances,
        "/switch_workspace": _lh.handle_switch_workspace,
        "/set_design_type": _lh.handle_set_design_type,
    })

    ROUTES["/reload"] = _handle_reload


def _handle_reload(body):
    """Hot-reload all handler modules and rebuild routes.

    Also discovers and imports any new handlers_*.py files not yet in
    sys.modules, so new handler files can be added without a full restart.
    """
    reloaded = []
    errors = []
    discovered = []

    # Capture live state from bridge_helpers BEFORE reload wipes it
    saved = {}
    for attr in ("_app", "frame_manager", "entity_resolver", "cad_state",
                 "graph_extractor", "patch_emitter", "action_executor"):
        saved[attr] = getattr(_bh, attr, None)

    for mod_name in _SUPPORT_MODULES:
        if mod_name in sys.modules:
            try:
                _il.reload(sys.modules[mod_name])
                reloaded.append(mod_name)
            except Exception as e:
                errors.append(f"{mod_name}: {e}")

    for mod_name in _HANDLER_MODULES:
        if mod_name in sys.modules:
            try:
                _il.reload(sys.modules[mod_name])
                reloaded.append(mod_name)
            except Exception as e:
                errors.append(f"{mod_name}: {e}")

    # Discover new handlers_*.py files not yet in sys.modules
    import glob as _glob
    handler_pattern = os.path.join(_THIS_DIR, "handlers_*.py")
    for filepath in _glob.glob(handler_pattern):
        mod_name = os.path.splitext(os.path.basename(filepath))[0]
        if mod_name not in sys.modules:
            try:
                mod = _il.import_module(mod_name)
                # Look for a *_ROUTES dict in the new module
                for attr_name in dir(mod):
                    if attr_name.endswith("_ROUTES") and isinstance(getattr(mod, attr_name), dict):
                        # Register it in _HANDLER_MODULES for future reloads
                        if mod_name not in _HANDLER_MODULES:
                            _HANDLER_MODULES[mod_name] = (attr_name,)
                        discovered.append(f"{mod_name} ({attr_name})")
                        break
                else:
                    discovered.append(f"{mod_name} (no ROUTES dict found)")
            except Exception as e:
                errors.append(f"discover {mod_name}: {e}")

    # Re-inject live state into freshly reloaded modules.
    # IMPORTANT: for nav-state classes whose source files were just reloaded
    # we need to *re-instantiate* from the freshly imported class object.
    # `from foo import Bar` caches the class, so even after importlib.reload(foo)
    # the saved instance still runs the old bytecode and code changes never
    # take effect. Recreate using the new class from sys.modules.
    _bh.set_app(app or saved.get("_app"))
    live_app = app or saved.get("_app")
    fm = saved.get("frame_manager")
    if fm:
        _bh.set_frame_manager(fm)

    def _fresh_class(mod_name, class_name):
        mod = sys.modules.get(mod_name)
        return getattr(mod, class_name, None) if mod else None

    er = saved.get("entity_resolver")
    cs = saved.get("cad_state")
    ge = saved.get("graph_extractor")
    pe = saved.get("patch_emitter")
    ae = saved.get("action_executor")

    # GraphExtractor is stateless aside from (app, entity_resolver) — safe to
    # re-instantiate from the fresh class so code changes take effect.
    GraphExtractor_fresh = _fresh_class("graph_extractor", "GraphExtractor")
    if GraphExtractor_fresh and live_app and er:
        try:
            ge = GraphExtractor_fresh(live_app, er)
        except Exception as e:
            errors.append(f"reinstantiate GraphExtractor: {e}")

    if er and cs and ge and pe and ae:
        _bh.set_nav_state(er, cs, ge, pe, ae)

    lh = sys.modules.get("_legacy_handlers")
    if lh:
        lh.app = app
        lh.ui = ui
        if fm: lh.frame_manager = fm
        for attr, val in [("entity_resolver", er), ("cad_state", cs),
                          ("graph_extractor", ge), ("patch_emitter", pe),
                          ("action_executor", ae)]:
            if val:
                setattr(lh, attr, val)

    _build_routes()
    return {
        "success": len(errors) == 0,
        "reloaded": reloaded,
        "discovered": discovered,
        "errors": errors,
        "total_routes": len(ROUTES),
    }

import handlers_viewer
_HANDLER_MODULES["handlers_viewer"] = ("VIEWER_ROUTES",)
_build_routes()


# ── Server lifecycle ──────────────────────────────────────────

def start_server():
    global server
    try:
        server = BoundedServer(("127.0.0.1", PORT), Handler, dispatcher)
        server.serve_forever()
    except Exception as e:
        if ui:
            _log(f"Server error: {str(e)}")


def run(context):
    global app, ui, server_thread, custom_event, custom_event_handler, dispatcher

    try:
        app = adsk.core.Application.get()
        ui = app.userInterface

        # Push app reference into shared helpers
        set_app(app)
        # Also push into legacy module so its globals work
        _lh.app = app
        _lh.ui = ui

        # Initialize frame manager
        fm = FrameManager()
        set_frame_manager(fm)
        _lh.frame_manager = fm

        # Initialize nav state system
        er = EntityResolver()
        cs = CADState(app, fm, er)
        ge = GraphExtractor(app, er)
        pe = PatchEmitter(app, cs)
        ae = ActionExecutor(app, cs, pe, ROUTES)
        set_nav_state(er, cs, ge, pe, ae)

        # Wire legacy globals
        _lh.entity_resolver = er
        _lh.cad_state = cs
        _lh.graph_extractor = ge
        _lh.patch_emitter = pe
        _lh.action_executor = ae

        pe.start()

        dispatcher = Dispatcher(
            _queue_event,
            collections.ChainMap({"/__ready": _readiness}, ROUTES),
            make_logger(os.path.join(_THIS_DIR, "bridge-requests.log")))

        # Register custom event for thread marshaling
        custom_event = app.registerCustomEvent("FusionMCPCommandEvent")
        custom_event_handler = CommandEventHandler()
        custom_event.add(custom_event_handler)

        event_stop.clear()
        threading.Thread(target=_event_pump, daemon=True).start()

        server_thread = threading.Thread(target=start_server, daemon=True)
        server_thread.start()

        _log(f"MCP Bridge running on localhost:{PORT}")

    except Exception as e:
        if ui:
            _log(f"Failed to start: {str(e)}\n{traceback.format_exc()}")


def stop(context):
    global server, ui, app, custom_event, custom_event_handler

    try:
        event_stop.set()
        if dispatcher:
            dispatcher.stop()

        if _bh.patch_emitter:
            _bh.patch_emitter.stop()

        if server:
            server.shutdown()
            server.server_close()
            server = None

        if custom_event:
            if custom_event_handler:
                custom_event.remove(custom_event_handler)
            app.unregisterCustomEvent("FusionMCPCommandEvent")
            custom_event = None
            custom_event_handler = None

        if ui:
            _log("MCP Bridge stopped")

    except Exception as e:
        if ui:
            _log(f"Error stopping: {str(e)}")
