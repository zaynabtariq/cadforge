"""Natural-language entry points. Offline grammar is deliberately bounded."""
from __future__ import annotations
import os
import re
from .schema import DesignSpec

SYSTEM = '''Translate the mechanical request into a typed parametric CAD specification in millimeters.
Supported families: glasses (camera and Pi Zero housing), enclosure, bracket, clip.
Parameters: wall, clearance, board_length, board_width, board_height, camera_diameter,
lid_thickness, screw_diameter, lens_width, lens_height, bridge, temple_length,
width, height, depth, hole_diameter, gap. Preserve explicit dimensions. Default Pi Zero
board envelope 65 x 30 x 6 mm; this is an assembly envelope assumption, not a verified
complete electronics assembly. Do not claim FEA, comfort, waterproofing, or fabrication readiness.
Do not silently turn a composite or unsupported part into a simpler supported family.'''

def parse_request(request: str) -> DesignSpec:
    low = request.lower()
    if any(x in low for x in ('glasses','spectacles','eyewear')):
        family = 'glasses'
    elif any(x in low for x in ('enclosure','housing','case')):
        family = 'enclosure'
    elif 'bracket' in low:
        family = 'bracket'
    elif 'clip' in low:
        family = 'clip'
    else:
        raise ValueError('Offline planner supports glasses, enclosure, bracket, or clip; supply a typed spec for exact control.')
    families = sum(bool(re.search(pattern, low)) for pattern in [r'\bglasses\b', r'\benclosure\b', r'\bbracket\b', r'\bclip\b'])
    if families > 1:
        raise ValueError('Composite natural-language requests require a new verified composition recipe.')
    params = {}
    for key in ('wall','clearance','board_length','board_width','board_height','camera_diameter','lid_thickness','screw_diameter','lens_width','lens_height','bridge','temple_length','width','height','depth','hole_diameter','gap'):
        label = key.replace('_', '[ _]')
        match = re.search(r'\b'+label+r'\s*(?:=|:|of)?\s*(-?\d+(?:\.\d+)?)\s*(mm|cm|in)?\b', low)
        if match:
            scale = {'mm':1, 'cm':10, 'in':25.4, None:1}[match[2]]
            params[key] = float(match[1]) * scale
    return DesignSpec(family=family, parameters=params)

def plan_with_model(request: str, model: str | None = None):
    from pydantic_ai import Agent
    from pydantic_ai.usage import UsageLimits, RunUsage
    from .model_budget import budgeted_model
    agent = Agent(budgeted_model(model or os.getenv('CADFORGE_MODEL','openai:gpt-4.1-mini-2025-04-14')), output_type=DesignSpec, system_prompt=SYSTEM, retries=1)
    usage = RunUsage()
    try:
        result = agent.run_sync(request, usage=usage, usage_limits=UsageLimits(request_limit=2, total_tokens_limit=5000), model_settings={'max_tokens':800, 'temperature':0, 'timeout':60})
    except Exception as error:
        error.cadforge_usage = {'input_tokens':usage.input_tokens,'output_tokens':usage.output_tokens,'requests':usage.requests}
        raise
    return result.output, {'input_tokens':usage.input_tokens,'output_tokens':usage.output_tokens,'requests':usage.requests}
