"""Design type management handlers (parametric vs direct)."""
import adsk.core
import adsk.fusion

try:
    from bridge_helpers import get_design
except ImportError:
    from .bridge_helpers import get_design


def handle_set_design_type(body):
    """Set design type to parametric or direct.

    Note: parametric -> direct destroys the timeline and is irreversible
    in the same document. direct -> parametric attempts conversion (may
    fail or have limitations).
    """
    design = get_design()
    if not design:
        raise Exception("No active design")

    target = body.get("type", "parametric").lower()
    if target == "parametric":
        target_type = adsk.fusion.DesignTypes.ParametricDesignType
    elif target == "direct":
        target_type = adsk.fusion.DesignTypes.DirectDesignType
    else:
        raise Exception(f"Unknown type: {target}. Use 'parametric' or 'direct'.")

    current_type = design.designType
    current_str = "parametric" if current_type == adsk.fusion.DesignTypes.ParametricDesignType else "direct"

    if current_type == target_type:
        return {"success": True, "already": target, "no_change": True}

    design.designType = target_type
    adsk.doEvents()
    new_type = design.designType
    new_str = "parametric" if new_type == adsk.fusion.DesignTypes.ParametricDesignType else "direct"

    return {
        "success": new_type == target_type,
        "previous": current_str,
        "current": new_str,
        "target": target,
    }


def handle_get_design_type(body):
    """Get current design type."""
    design = get_design()
    if not design:
        raise Exception("No active design")

    current_type = design.designType
    type_str = "parametric" if current_type == adsk.fusion.DesignTypes.ParametricDesignType else "direct"
    return {"type": type_str}


def handle_set_design_intent(body):
    design = get_design()
    types = {
        'hybrid': adsk.fusion.DesignIntentTypes.HybridDesignIntentType,
        'part': adsk.fusion.DesignIntentTypes.PartDesignIntentType,
        'assembly': adsk.fusion.DesignIntentTypes.AssemblyDesignIntentType,
    }
    target = body['intent']
    design.designIntent = types[target]
    return {'success': design.designIntent == types[target], 'intent': target}


DESIGN_ROUTES = {
    "/set_design_intent": handle_set_design_intent,
    "/set_design_type": handle_set_design_type,
    "/get_design_type": handle_get_design_type,
}
