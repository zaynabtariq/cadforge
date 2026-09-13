"""Data Panel & Document management handlers for Fusion 360 MCP Bridge.

Browse the cloud Data Panel (hubs, projects, folders, files), open designs
by name, and manage open documents — all without touching the Fusion UI.

Endpoints (6):
  DATA PANEL
    /list_projects       – list all projects in the user's hub
    /list_folder         – list files + subfolders in a project folder
    /search_files        – search for files by name across projects
    /open_project_file   – open a cloud file by project+path or name
  DOCUMENTS
    /list_open_documents – list all currently open documents
    /activate_document   – switch to an already-open document
  MESH IMPORT
    /import_mesh         – insert STL/OBJ/3MF as a MeshBody in active design
"""

import os
import traceback

import adsk.core
import adsk.fusion

import bridge_helpers as _bh


# ── helpers ──────────────────────────────────────────────────

def _get_app():
    if not _bh.app:
        raise Exception("Fusion app not initialized")
    return _bh.app


def _get_hub():
    app = _get_app()
    hub = app.data.dataHubs.item(0)
    if not hub:
        raise Exception("No data hub available — are you signed in?")
    return hub


def _find_project(name=None, project_id=None):
    """Find a project by name or ID."""
    hub = _get_hub()
    projects = hub.dataProjects
    for i in range(projects.count):
        p = projects.item(i)
        if project_id and p.id == project_id:
            return p
        if name and p.name == name:
            return p
    identifier = project_id or name
    raise Exception(f"Project not found: {identifier}")


def _walk_folder_path(root_folder, path):
    """Walk a '/'-separated path from root_folder. Returns the target folder."""
    if not path or path in ("", "/"):
        return root_folder
    segments = [s for s in path.split("/") if s]
    folder = root_folder
    for seg in segments:
        found = None
        for i in range(folder.dataFolders.count):
            f = folder.dataFolders.item(i)
            if f.name == seg:
                found = f
                break
        if not found:
            raise Exception(f"Folder not found: '{seg}' in '{folder.name}'")
        folder = found
    return folder


def _file_info(data_file, folder_path=""):
    """Serialize a DataFile to a dict."""
    info = {
        "name": data_file.name,
        "id": data_file.id,
        "version": data_file.versionNumber,
    }
    try:
        info["date_modified"] = data_file.dateModified.isoformat()
    except Exception:
        info["date_modified"] = None
    try:
        info["file_extension"] = data_file.fileExtension
    except Exception:
        info["file_extension"] = None
    if folder_path:
        info["folder_path"] = folder_path
    return info


def _folder_info(data_folder):
    """Serialize a DataFolder to a dict."""
    return {
        "name": data_folder.name,
        "id": data_folder.id,
    }


# ── DATA PANEL handlers ─────────────────────────────────────

def handle_list_projects(body):
    """List all projects in the user's hub."""
    try:
        hub = _get_hub()
        projects = hub.dataProjects
        result = []
        for i in range(projects.count):
            p = projects.item(i)
            result.append({
                "name": p.name,
                "id": p.id,
            })
        return {"projects": result, "count": len(result), "hub": hub.name}
    except Exception as e:
        return {"error": True, "message": str(e), "traceback": traceback.format_exc()}


def handle_list_folder(body):
    """List files and subfolders in a project folder.

    Params:
        project_name or project_id  (required)
        folder_path                 (optional, e.g. "Subfolder/Nested")
    """
    try:
        project = _find_project(
            name=body.get("project_name"),
            project_id=body.get("project_id"),
        )
        root = project.rootFolder
        folder = _walk_folder_path(root, body.get("folder_path", ""))

        files = []
        for i in range(folder.dataFiles.count):
            files.append(_file_info(folder.dataFiles.item(i)))

        folders = []
        for i in range(folder.dataFolders.count):
            folders.append(_folder_info(folder.dataFolders.item(i)))

        return {
            "folder_name": folder.name,
            "project": project.name,
            "files": files,
            "folders": folders,
            "file_count": len(files),
            "folder_count": len(folders),
        }
    except Exception as e:
        return {"error": True, "message": str(e), "traceback": traceback.format_exc()}


def handle_create_folder(body):
    """Create a new folder in a project.

    Params:
        project_name or project_id  (required)
        folder_path                 (optional, parent folder path)
        name                        (required, new folder name)
    """
    try:
        project = _find_project(
            name=body.get("project_name"),
            project_id=body.get("project_id"),
        )
        root = project.rootFolder
        parent = _walk_folder_path(root, body.get("folder_path", ""))
        new_folder = parent.dataFolders.add(body["name"])
        return {
            "success": True,
            "name": new_folder.name,
            "id": new_folder.id,
            "parent": parent.name,
        }
    except Exception as e:
        return {"error": True, "message": str(e), "traceback": traceback.format_exc()}


def handle_search_files(body):
    """Search for files by name across one or all projects.

    Params:
        query          (required) – substring to match (case-insensitive)
        project_name   (optional) – limit search to one project
        project_id     (optional) – limit search to one project
        max_results    (optional, default 20)
    """
    try:
        query = body.get("query")
        if not query:
            raise Exception("query is required")
        query_lower = query.lower()
        max_results = body.get("max_results", 20)

        # Determine scope
        if body.get("project_name") or body.get("project_id"):
            projects = [_find_project(
                name=body.get("project_name"),
                project_id=body.get("project_id"),
            )]
        else:
            hub = _get_hub()
            all_proj = hub.dataProjects
            projects = [all_proj.item(i) for i in range(all_proj.count)]

        results = []

        def _search_folder(folder, project_name, path_prefix):
            if len(results) >= max_results:
                return
            for i in range(folder.dataFiles.count):
                if len(results) >= max_results:
                    return
                f = folder.dataFiles.item(i)
                if query_lower in f.name.lower():
                    info = _file_info(f, folder_path=path_prefix)
                    info["project"] = project_name
                    results.append(info)
            for i in range(folder.dataFolders.count):
                if len(results) >= max_results:
                    return
                sf = folder.dataFolders.item(i)
                child_path = f"{path_prefix}/{sf.name}" if path_prefix else sf.name
                _search_folder(sf, project_name, child_path)

        for proj in projects:
            if len(results) >= max_results:
                break
            _search_folder(proj.rootFolder, proj.name, "")

        return {"results": results, "count": len(results), "query": query}
    except Exception as e:
        return {"error": True, "message": str(e), "traceback": traceback.format_exc()}


def handle_open_project_file(body):
    """Open a cloud file from the Data Panel.

    Params (one of):
        project_name + file_name   – find by name in project root (or folder_path)
        project_name + folder_path + file_name
        project_id   + file_name
        file_id + project_name     – open by direct file ID
    """
    try:
        app = _get_app()
        data_file = None

        file_id = body.get("file_id")
        file_name = body.get("file_name")

        if file_id:
            # Search for file by ID across specified project (or all projects)
            if body.get("project_name") or body.get("project_id"):
                projects = [_find_project(
                    name=body.get("project_name"),
                    project_id=body.get("project_id"),
                )]
            else:
                hub = _get_hub()
                all_proj = hub.dataProjects
                projects = [all_proj.item(i) for i in range(all_proj.count)]

            def _find_by_id(folder):
                for i in range(folder.dataFiles.count):
                    f = folder.dataFiles.item(i)
                    if f.id == file_id:
                        return f
                for i in range(folder.dataFolders.count):
                    result = _find_by_id(folder.dataFolders.item(i))
                    if result:
                        return result
                return None

            for proj in projects:
                data_file = _find_by_id(proj.rootFolder)
                if data_file:
                    break

        elif file_name:
            project = _find_project(
                name=body.get("project_name"),
                project_id=body.get("project_id"),
            )
            folder = _walk_folder_path(
                project.rootFolder, body.get("folder_path", ""))
            # Find the file by name in the folder
            for i in range(folder.dataFiles.count):
                f = folder.dataFiles.item(i)
                if f.name == file_name:
                    data_file = f
                    break
            if not data_file:
                # Try partial match
                for i in range(folder.dataFiles.count):
                    f = folder.dataFiles.item(i)
                    if file_name.lower() in f.name.lower():
                        data_file = f
                        break
        else:
            raise Exception("file_name or file_id is required")

        if not data_file:
            raise Exception(f"File not found: {file_name or file_id}")

        # Open the file
        doc = app.documents.open(data_file)
        if not doc:
            raise Exception("Failed to open document")

        adsk.doEvents()

        # Gather design info
        design = app.activeProduct
        bodies = []
        components = []
        if design and hasattr(design, 'rootComponent'):
            root = design.rootComponent
            for b in root.bRepBodies:
                bodies.append(b.name)
            for i in range(root.occurrences.count):
                occ = root.occurrences.item(i)
                components.append(occ.component.name)

        return {
            "success": True,
            "document_name": doc.name,
            "file_name": data_file.name,
            "file_id": data_file.id,
            "version": data_file.versionNumber,
            "bodies": bodies,
            "components": components,
            "message": f"Opened '{data_file.name}'",
        }
    except Exception as e:
        return {"error": True, "message": str(e), "traceback": traceback.format_exc()}


# ── DOCUMENT management handlers ────────────────────────────

def handle_save(body):
    """Save the active document (must already have been saved/named).

    No params required — saves the current document in-place.
    """
    try:
        app = _get_app()
        doc = app.activeDocument
        if not doc:
            raise Exception("No active document")

        doc.save("")
        adsk.doEvents()

        return {
            "success": True,
            "document_name": doc.name,
            "message": f"Saved '{doc.name}'",
        }
    except Exception as e:
        return {"error": True, "message": str(e), "traceback": traceback.format_exc()}


def handle_save_as(body):
    """Save the active document to a project with a given name.

    Params:
        name            (required) – file name
        project_name    (required) – target project
        folder_path     (optional) – subfolder path within the project
    """
    try:
        app = _get_app()
        doc = app.activeDocument
        if not doc:
            raise Exception("No active document")

        name = body.get("name")
        if not name:
            raise Exception("name is required")

        project = _find_project(
            name=body.get("project_name"),
            project_id=body.get("project_id"),
        )
        root_folder = project.rootFolder
        folder = _walk_folder_path(root_folder, body.get("folder_path", ""))

        doc.saveAs(name, folder, "", "")
        adsk.doEvents()

        return {
            "success": True,
            "name": name,
            "project": project.name,
            "folder": folder.name,
            "message": f"Saved '{name}' to {project.name}/{folder.name}",
        }
    except Exception as e:
        return {"error": True, "message": str(e), "traceback": traceback.format_exc()}


def handle_list_open_documents(body):
    """List all currently open documents."""
    try:
        app = _get_app()
        docs = app.documents
        active_name = None
        if app.activeDocument:
            active_name = app.activeDocument.name

        result = []
        for i in range(docs.count):
            d = docs.item(i)
            info = {
                "name": d.name,
                "is_saved": d.isSaved,
                "is_active": (d.name == active_name),
            }
            try:
                info["data_file_id"] = d.dataFile.id if d.dataFile else None
            except Exception:
                info["data_file_id"] = None
            result.append(info)

        return {
            "documents": result,
            "count": len(result),
            "active_document": active_name,
        }
    except Exception as e:
        return {"error": True, "message": str(e), "traceback": traceback.format_exc()}


def handle_activate_document(body):
    """Switch to an already-open document.

    Params:
        document_name  (required) – name of the open document to activate
    """
    try:
        app = _get_app()
        doc_name = body.get("document_name")
        if not doc_name:
            raise Exception("document_name is required")

        docs = app.documents
        target = None
        for i in range(docs.count):
            d = docs.item(i)
            if d.name == doc_name:
                target = d
                break

        if not target:
            # Partial match fallback
            for i in range(docs.count):
                d = docs.item(i)
                if doc_name.lower() in d.name.lower():
                    target = d
                    break

        if not target:
            names = [docs.item(i).name for i in range(docs.count)]
            raise Exception(
                f"Document '{doc_name}' not found. Open documents: {names}")

        target.activate()
        adsk.doEvents()

        return {
            "success": True,
            "activated": target.name,
            "message": f"Switched to '{target.name}'",
        }
    except Exception as e:
        return {"error": True, "message": str(e), "traceback": traceback.format_exc()}


def handle_close_document(body):
    """Close a document.

    Params:
        document_name  (required) – name of the document to close
        save           (optional, default false) – save before closing
    """
    try:
        app = _get_app()
        doc_name = body.get("document_name")
        if not doc_name:
            raise Exception("document_name is required")
        save = body.get("save", False)

        docs = app.documents
        target = None
        for i in range(docs.count):
            d = docs.item(i)
            if d.name == doc_name:
                target = d
                break

        if not target:
            for i in range(docs.count):
                d = docs.item(i)
                if doc_name.lower() in d.name.lower():
                    target = d
                    break

        if not target:
            names = [docs.item(i).name for i in range(docs.count)]
            raise Exception(
                f"Document '{doc_name}' not found. Open documents: {names}")

        name = target.name
        target.close(save)
        adsk.doEvents()

        return {
            "success": True,
            "closed": name,
            "saved": save,
            "message": f"Closed '{name}'" + (" (saved)" if save else " (without saving)"),
        }
    except Exception as e:
        return {"error": True, "message": str(e), "traceback": traceback.format_exc()}


# ── INSERT (assembly reference) ──────────────────────────────

def handle_insert_into_assembly(body):
    """Insert a design from the Data Panel into the active assembly.

    Params:
        project_name   (required) – project containing the part
        file_name      (required) – name of the file to insert
        folder_path    (optional) – subfolder path
        translate      (optional) – [x, y, z] in mm to position the part
        rotate_axis    (optional) – rotation axis: "x", "y", "z" or [x,y,z] vector
        rotate_angle   (optional) – rotation angle in degrees
    """
    try:
        import time
        app = _get_app()

        # Find the DataFile
        project = _find_project(
            name=body.get("project_name"),
            project_id=body.get("project_id"),
        )
        folder = _walk_folder_path(
            project.rootFolder, body.get("folder_path", ""))

        file_name = body.get("file_name")
        if not file_name:
            raise Exception("file_name is required")

        data_file = None
        for i in range(folder.dataFiles.count):
            f = folder.dataFiles.item(i)
            if f.name == file_name:
                data_file = f
                break
        if not data_file:
            for i in range(folder.dataFiles.count):
                f = folder.dataFiles.item(i)
                if file_name.lower() in f.name.lower():
                    data_file = f
                    break
        if not data_file:
            raise Exception(f"File '{file_name}' not found in {project.name}/{folder.name}")

        # Insert into the active design
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            raise Exception("No active design")
        root = design.rootComponent

        # Create a transform matrix (identity, then apply rotation + translation)
        transform = adsk.core.Matrix3D.create()

        # Apply rotation if specified
        rotate_axis = body.get("rotate_axis")
        rotate_angle = body.get("rotate_angle")
        if rotate_axis is not None and rotate_angle is not None:
            import math
            angle_rad = math.radians(float(rotate_angle))
            # Parse axis: string shorthand or [x,y,z] vector
            if isinstance(rotate_axis, str):
                axis_map = {
                    "x": (1, 0, 0), "X": (1, 0, 0),
                    "y": (0, 1, 0), "Y": (0, 1, 0),
                    "z": (0, 0, 1), "Z": (0, 0, 1),
                }
                ax = axis_map.get(rotate_axis)
                if not ax:
                    raise Exception(
                        f"Invalid rotate_axis '{rotate_axis}'. "
                        f"Use 'x', 'y', 'z' or [x,y,z] vector.")
            else:
                ax = (float(rotate_axis[0]), float(rotate_axis[1]), float(rotate_axis[2]))
            axis_vec = adsk.core.Vector3D.create(ax[0], ax[1], ax[2])
            origin_pt = adsk.core.Point3D.create(0, 0, 0)
            transform.setToRotation(angle_rad, axis_vec, origin_pt)

        translate = body.get("translate")
        if translate and len(translate) == 3:
            # Get current translation (may be zero or set by rotation)
            cur = transform.translation
            transform.translation = adsk.core.Vector3D.create(
                cur.x + translate[0] / 10.0,
                cur.y + translate[1] / 10.0,
                cur.z + translate[2] / 10.0)

        occ = root.occurrences.addByInsert(
            data_file, transform, True)
        adsk.doEvents()
        time.sleep(0.5)
        adsk.doEvents()

        # Gather info about the inserted component
        comp = occ.component
        bodies = [b.name for b in comp.bRepBodies]

        return {
            "success": True,
            "occurrence": occ.name,
            "component": comp.name,
            "bodies": bodies,
            "body_count": len(bodies),
            "message": f"Inserted '{file_name}' as '{occ.name}'",
        }
    except Exception as e:
        return {"error": True, "message": str(e), "traceback": traceback.format_exc()}


# ── DERIVE (cross-document copy) ─────────────────────────────

def handle_derive_from_document(body):
    """Derive bodies from an open document into the active document using
    Fusion's Derive feature (proper cross-document copy).

    Params:
        source_document  (required) – name of the source document (must be open/saved)
        body_name        (required) – body name(s) to include; comma-separated for multiple
                                      e.g. "A,B,C"
        new_name         (optional) – rename the derived body (only for single-body derive)
    """
    try:
        import time
        import tempfile
        import os
        app = _get_app()

        source_doc_name = body.get("source_document")
        body_name_raw = body.get("body_name")
        if not source_doc_name:
            raise Exception("source_document is required")
        if not body_name_raw:
            raise Exception("body_name is required")

        # Support multi-body: "A,B,C" or ["A","B","C"]
        if isinstance(body_name_raw, str):
            body_names = [n.strip() for n in body_name_raw.split(",") if n.strip()]
        elif isinstance(body_name_raw, list):
            body_names = body_name_raw
        else:
            body_names = [str(body_name_raw)]

        # Remember the target (current) document
        target_doc = app.activeDocument

        # Find the source document
        docs = app.documents
        source_doc = None
        for i in range(docs.count):
            d = docs.item(i)
            if d.name == source_doc_name or source_doc_name.lower() in d.name.lower():
                source_doc = d
                break
        if not source_doc:
            names = [docs.item(i).name for i in range(docs.count)]
            raise Exception(
                f"Source document '{source_doc_name}' not found. Open: {names}")

        # Activate source to export the body as a temp file
        source_doc.activate()
        adsk.doEvents()
        time.sleep(0.5)
        adsk.doEvents()

        source_design = adsk.fusion.Design.cast(app.activeProduct)
        if not source_design:
            raise Exception("Source document has no Design")
        source_root = source_design.rootComponent

        # Find all requested bodies
        source_bodies = []
        not_found = []
        for bname in body_names:
            found_body = None
            for b in source_root.bRepBodies:
                if b.name == bname:
                    found_body = b
                    break
            if not found_body:
                for occ in source_root.allOccurrences:
                    for b in occ.bRepBodies:
                        if b.name == bname:
                            found_body = b
                            break
                    if found_body:
                        break
            if found_body:
                source_bodies.append(found_body)
            else:
                not_found.append(bname)

        if not source_bodies:
            available = [b.name for b in source_root.bRepBodies]
            for occ in source_root.allOccurrences:
                for b in occ.bRepBodies:
                    available.append(f"{occ.component.name}/{b.name}")
            target_doc.activate()
            raise Exception(
                f"No bodies found matching {body_names}. Available: {available}")

        # Record source positions for all bodies
        source_positions = {}
        for sb in source_bodies:
            bbox = sb.boundingBox
            source_positions[sb.name] = {
                "min": [round(bbox.minPoint.x * 10, 2),
                        round(bbox.minPoint.y * 10, 2),
                        round(bbox.minPoint.z * 10, 2)],
                "max": [round(bbox.maxPoint.x * 10, 2),
                        round(bbox.maxPoint.y * 10, 2),
                        round(bbox.maxPoint.z * 10, 2)],
            }

        # Switch back to target document
        target_doc.activate()
        adsk.doEvents()
        time.sleep(0.5)
        adsk.doEvents()

        # Use the Derive feature to bring in the bodies
        target_design = adsk.fusion.Design.cast(app.activeProduct)
        target_root = target_design.rootComponent
        derive_features = target_root.features.deriveFeatures

        # Record body count before derive to identify new bodies
        bodies_before = set()
        for b in target_root.bRepBodies:
            bodies_before.add(b.name)

        # Create derive input from source Design object
        derive_input = derive_features.createInput(source_design)

        # sourceEntities accepts a list of Base pointers — pass all bodies
        derive_input.sourceEntities = source_bodies

        # Execute the derive
        derive_feature = derive_features.add(derive_input)
        adsk.doEvents()
        time.sleep(0.5)
        adsk.doEvents()

        # Search for all derived bodies
        all_derived = []
        new_bodies_map = {}  # name -> body object

        # Root bodies
        for b in target_root.bRepBodies:
            if b.name not in bodies_before:
                all_derived.append({"name": b.name, "location": "root"})
                if b.name in body_names:
                    new_bodies_map[b.name] = b

        # All occurrences (including nested)
        for occ in target_root.allOccurrences:
            comp = occ.component
            for j in range(comp.bRepBodies.count):
                b = comp.bRepBodies.item(j)
                loc = f"{occ.fullPathName}/{b.name}"
                all_derived.append({"name": b.name, "location": loc})
                if b.name in body_names and b.name not in new_bodies_map:
                    new_bodies_map[b.name] = b

        # Rename if single body and new_name provided
        derived_name = body.get("new_name")
        if derived_name and len(body_names) == 1 and body_names[0] in new_bodies_map:
            new_bodies_map[body_names[0]].name = derived_name

        # Build per-body result info
        derived_results = []
        for bname in body_names:
            nb = new_bodies_map.get(bname)
            if nb:
                bbox = nb.boundingBox
                derived_results.append({
                    "body_name": nb.name,
                    "found": True,
                    "dimensions_mm": {
                        "x": round((bbox.maxPoint.x - bbox.minPoint.x) * 10, 2),
                        "y": round((bbox.maxPoint.y - bbox.minPoint.y) * 10, 2),
                        "z": round((bbox.maxPoint.z - bbox.minPoint.z) * 10, 2),
                    },
                    "position_mm": {
                        "min": [round(bbox.minPoint.x * 10, 2),
                                round(bbox.minPoint.y * 10, 2),
                                round(bbox.minPoint.z * 10, 2)],
                        "max": [round(bbox.maxPoint.x * 10, 2),
                                round(bbox.maxPoint.y * 10, 2),
                                round(bbox.maxPoint.z * 10, 2)],
                    },
                })
            else:
                derived_results.append({"body_name": bname, "found": False})

        # Backward-compatible single-body fields
        first_name = body_names[0]
        single_body = new_bodies_map.get(first_name)
        if single_body:
            bbox = single_body.boundingBox
            dims = {
                "x": round((bbox.maxPoint.x - bbox.minPoint.x) * 10, 2),
                "y": round((bbox.maxPoint.y - bbox.minPoint.y) * 10, 2),
                "z": round((bbox.maxPoint.z - bbox.minPoint.z) * 10, 2),
            }
            position = {
                "min": [round(bbox.minPoint.x * 10, 2),
                        round(bbox.minPoint.y * 10, 2),
                        round(bbox.minPoint.z * 10, 2)],
                "max": [round(bbox.maxPoint.x * 10, 2),
                        round(bbox.maxPoint.y * 10, 2),
                        round(bbox.maxPoint.z * 10, 2)],
            }
        else:
            dims = {}
            position = {}

        return {
            "success": True,
            "body_name": derived_name or first_name,
            "body_found": single_body is not None,
            "body_count": len(source_bodies),
            "dimensions_mm": dims,
            "position_mm": position,
            "source_positions_mm": source_positions,
            "derived_bodies": derived_results,
            "not_found": not_found,
            "all_derived_bodies": all_derived,
            "message": f"Derived {len(source_bodies)} body(ies) from '{source_doc_name}'",
        }
    except Exception as e:
        return {"error": True, "message": str(e), "traceback": traceback.format_exc()}


# ── Reference updates ────────────────────────────────────────

def handle_update_references(body):
    """Update external references in the active assembly to their latest versions.

    Uses two strategies:
    1. Version comparison via DataFile API — detects and updates stale references
    2. Fallback: finds the source document among open documents and compares
       version numbers, triggering a re-open if newer

    Params:
        component (optional) – update only this component's reference
    """
    try:
        design = _bh.get_design()
        root = _bh.get_root()
        app = adsk.core.Application.get()
        target_name = body.get("component")

        updated = []
        skipped = []
        errors = []

        # Build map of open documents by name for version comparison
        open_docs = {}
        for i in range(app.documents.count):
            doc = app.documents.item(i)
            try:
                if doc.dataFile:
                    open_docs[doc.name] = {
                        "version": doc.dataFile.versionNumber,
                        "doc": doc,
                    }
            except Exception:
                pass

        for i in range(root.allOccurrences.count):
            occ = root.allOccurrences.item(i)
            comp = occ.component
            comp_name = comp.name

            if target_name and target_name.lower() not in comp_name.lower():
                continue

            try:
                # Strategy 1: check the component's linked document version
                linked_doc = comp.parentDesign.parentDocument
                if not linked_doc or not linked_doc.dataFile:
                    skipped.append({"component": comp_name, "reason": "no linked document"})
                    continue

                linked_df = linked_doc.dataFile
                linked_ver = linked_df.versionNumber

                # Strategy 2: find the source in open docs and compare
                source_info = open_docs.get(comp_name)
                if source_info and source_info["version"] > linked_ver:
                    # Source doc is newer — the assembly ref is stale
                    # Try to update via getLatestVersion
                    try:
                        occ.documentReference.getLatestVersion()
                        updated.append({
                            "component": comp_name,
                            "from_version": linked_ver,
                            "to_version": source_info["version"],
                            "method": "getLatestVersion",
                        })
                    except Exception as e2:
                        errors.append({
                            "component": comp_name,
                            "stale": True,
                            "assembly_version": linked_ver,
                            "source_version": source_info["version"],
                            "error": str(e2),
                            "hint": "Right-click component in browser → Get Latest",
                        })
                else:
                    skipped.append({
                        "component": comp_name,
                        "version": linked_ver,
                        "reason": "up to date",
                    })
            except Exception as e:
                errors.append({"component": comp_name, "error": str(e)})

        adsk.doEvents()

        return {
            "success": True,
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
            "message": f"Updated {len(updated)} reference(s), "
                       f"skipped {len(skipped)}, errors {len(errors)}",
        }
    except Exception as e:
        return {"error": True, "message": str(e), "traceback": traceback.format_exc()}


# ── Mesh import ──────────────────────────────────────────────

def handle_import_mesh(body):
    """Insert an STL/OBJ/3MF mesh as a MeshBody in the active design.

    Args (request body):
        path:      filesystem path to the mesh file (required)
        units:     mm | cm | m | in | ft (default: mm)
        component: target component name (default: rootComponent)
        name:      rename the imported mesh body
    """
    try:
        app = _get_app()
        product = app.activeProduct
        design = adsk.fusion.Design.cast(product)
        if not design:
            raise Exception("Active product is not a Fusion design")

        path = body.get("path")
        if not path:
            raise Exception("'path' is required")
        path = os.path.expanduser(path)
        if not os.path.exists(path):
            raise Exception(f"File not found: {path}")

        units_str = (body.get("units") or "mm").lower()
        units_map = {
            "mm": adsk.fusion.MeshUnits.MillimeterMeshUnit,
            "cm": adsk.fusion.MeshUnits.CentimeterMeshUnit,
            "m":  adsk.fusion.MeshUnits.MeterMeshUnit,
            "in": adsk.fusion.MeshUnits.InchMeshUnit,
            "ft": adsk.fusion.MeshUnits.FootMeshUnit,
        }
        mesh_unit = units_map.get(units_str)
        if mesh_unit is None:
            raise Exception(f"Unsupported units '{units_str}'. Use one of: mm, cm, m, in, ft")

        # Pick target component
        target = design.rootComponent
        comp_name = body.get("component")
        if comp_name and comp_name != target.name:
            for occ in design.rootComponent.allOccurrences:
                if occ.component.name == comp_name:
                    target = occ.component
                    break

        # In a parametric design, mesh import has to be wrapped in a BaseFeature.
        is_parametric = (design.designType == adsk.fusion.DesignTypes.ParametricDesignType)

        # MeshBodies.add(filename, units) takes the file path directly.
        # In parametric mode it must be wrapped in a BaseFeature edit.
        if is_parametric:
            base = target.features.baseFeatures.add()
            base.startEdit()
            try:
                new_meshes = target.meshBodies.add(path, mesh_unit, base)
            finally:
                base.finishEdit()
        else:
            new_meshes = target.meshBodies.add(path, mesh_unit)

        adsk.doEvents()

        new_name = body.get("name")
        results = []
        for i in range(new_meshes.count):
            mb = new_meshes.item(i)
            if new_name:
                mb.name = new_name if new_meshes.count == 1 else f"{new_name}_{i}"

            bbox_info = None
            try:
                bb = mb.boundingBox
                # Fusion API returns lengths in cm; convert to mm.
                bbox_info = {
                    "min_mm": [bb.minPoint.x * 10, bb.minPoint.y * 10, bb.minPoint.z * 10],
                    "max_mm": [bb.maxPoint.x * 10, bb.maxPoint.y * 10, bb.maxPoint.z * 10],
                    "size_mm": [
                        (bb.maxPoint.x - bb.minPoint.x) * 10,
                        (bb.maxPoint.y - bb.minPoint.y) * 10,
                        (bb.maxPoint.z - bb.minPoint.z) * 10,
                    ],
                }
            except Exception:
                pass

            tri_count = None
            try:
                tri_count = mb.mesh.triangleCount
            except Exception:
                pass

            results.append({
                "name": mb.name,
                "triangle_count": tri_count,
                "bbox": bbox_info,
            })

        return {
            "success": True,
            "imported": len(results),
            "meshes": results,
            "file": path,
            "units": units_str,
            "component": target.name,
            "wrapped_in_base_feature": is_parametric,
        }
    except Exception as e:
        return {"error": True, "message": str(e), "traceback": traceback.format_exc()}


# ── Route table ──────────────────────────────────────────────

def handle_list_versions(body):
    """List all versions of a file in the Data Panel.

    Params:
        project_name + file_name
    Returns list of versions with version number, date, and description.
    """
    app = _get_app()
    project = _find_project(name=body.get("project_name"))
    folder = _walk_folder_path(project.rootFolder, body.get("folder_path", ""))
    file_name = body["file_name"]
    data_file = None
    for i in range(folder.dataFiles.count):
        f = folder.dataFiles.item(i)
        if f.name == file_name or file_name.lower() in f.name.lower():
            data_file = f
            break
    if not data_file:
        raise Exception(f"File not found: {file_name}")

    versions = data_file.versions
    result = []
    for i in range(versions.count):
        v = versions.item(i)
        info = {
            "version": v.versionNumber,
            "id": v.id,
        }
        try:
            info["date_modified"] = v.dateModified.isoformat()
        except Exception:
            info["date_modified"] = None
        try:
            info["description"] = v.description
        except Exception:
            info["description"] = None
        result.append(info)
    return {"file_name": data_file.name, "versions": result, "count": len(result)}


def handle_open_version(body):
    """Open a specific version of a file.

    Params:
        project_name + file_name + version  (version number)
    """
    app = _get_app()
    project = _find_project(name=body.get("project_name"))
    folder = _walk_folder_path(project.rootFolder, body.get("folder_path", ""))
    file_name = body["file_name"]
    target_version = body["version"]
    data_file = None
    for i in range(folder.dataFiles.count):
        f = folder.dataFiles.item(i)
        if f.name == file_name or file_name.lower() in f.name.lower():
            data_file = f
            break
    if not data_file:
        raise Exception(f"File not found: {file_name}")

    versions = data_file.versions
    target_df = None
    for i in range(versions.count):
        v = versions.item(i)
        if v.versionNumber == target_version:
            target_df = v
            break
    if not target_df:
        raise Exception(f"Version {target_version} not found")

    doc = app.documents.open(target_df)
    if not doc:
        raise Exception(f"Failed to open version {target_version}")
    adsk.doEvents()

    design = doc.products.itemByProductType("DesignProductType")
    body_names = []
    if design:
        root = design.rootComponent
        for i in range(root.bRepBodies.count):
            body_names.append(root.bRepBodies.item(i).name)

    timeline_count = 0
    if design and design.timeline:
        timeline_count = design.timeline.count

    return {
        "success": True,
        "file_name": data_file.name,
        "version": target_version,
        "bodies": body_names,
        "timeline_count": timeline_count,
    }


DATA_ROUTES = {
    "/list_projects":         handle_list_projects,
    "/list_folder":           handle_list_folder,
    "/create_folder":         handle_create_folder,
    "/search_files":          handle_search_files,
    "/open_project_file":     handle_open_project_file,
    "/list_open_documents":   handle_list_open_documents,
    "/data_save":             handle_save,
    "/save_as":               handle_save_as,
    "/activate_document":     handle_activate_document,
    "/close_document":        handle_close_document,
    "/insert_into_assembly":  handle_insert_into_assembly,
    "/derive_from_document":  handle_derive_from_document,
    "/update_references":     handle_update_references,
    "/import_mesh":           handle_import_mesh,
    "/list_versions":         handle_list_versions,
    "/open_version":          handle_open_version,
}
