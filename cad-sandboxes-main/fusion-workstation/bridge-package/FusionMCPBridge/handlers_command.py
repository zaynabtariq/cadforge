"""Command definition execution handlers.

Lets us invoke Fusion UI commands programmatically by ID.
This is a workaround for missing Python API methods (e.g., T-Spline primitives).
"""
import adsk.core
import adsk.fusion

try:
    import bridge_helpers as _bh
except ImportError:
    from . import bridge_helpers as _bh


def handle_list_commands(body):
    """List command definitions matching a filter."""
    app = _bh.app
    ui = app.userInterface
    cmds = ui.commandDefinitions

    pattern = body.get("pattern", "").lower()
    limit = body.get("limit", 50)

    matches = []
    for i in range(cmds.count):
        c = cmds.item(i)
        cid = c.id
        if pattern and pattern not in cid.lower():
            continue
        matches.append({"id": cid, "name": c.name if hasattr(c, "name") else None})
        if len(matches) >= limit:
            break

    return {"commands": matches, "count": len(matches), "total": cmds.count}


def handle_execute_command(body):
    """Execute a command definition by ID. Optionally pass input values."""
    app = _bh.app
    ui = app.userInterface
    cmd_id = body.get("id")
    if not cmd_id:
        raise Exception("id is required")

    cmd_def = ui.commandDefinitions.itemById(cmd_id)
    if not cmd_def:
        raise Exception(f"Command not found: {cmd_id}")

    # Execute the command
    cmd_def.execute()
    adsk.doEvents()

    return {"executed": True, "id": cmd_id, "name": cmd_def.name if hasattr(cmd_def, "name") else None}


def handle_text_command(body):
    """Execute a text command via Fusion's text command palette.

    Text commands can do things the regular Python API can't, like
    creating T-Spline primitives without a UI dialog.
    """
    app = _bh.app
    command = body.get("command")
    if not command:
        raise Exception("command is required")

    result = app.executeTextCommand(command)
    adsk.doEvents()
    return {"result": result, "command": command}


COMMAND_ROUTES = {
    "/list_commands": handle_list_commands,
    "/execute_command": handle_execute_command,
    "/text_command": handle_text_command,
}
