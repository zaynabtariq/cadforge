"""Bounded natural-language counterbores anchored to recognized hole rims."""
import hashlib
from pathlib import Path
import re


def plan_counterbore(request,selection,state):
    if not re.search(r'\bcounterbore\b',request,re.I):return None
    from .edit_planner import LENGTH,_mm,Counterbore,_measurement_guard
    def clarify(text):return {'command':None,'clarification':text,'explanation':text,'planner':'counterbore_guard','usage':{'model_requests':0,'input_tokens':0,'output_tokens':0}}
    low=request.lower()
    numeric_guard=_measurement_guard(low)
    if numeric_guard:return clarify(numeric_guard.clarification)
    if re.search(r'[<>≤≥≈±~]',low):
        return clarify('Specify exact counterbore dimensions. Inequalities, ranges and approximate tolerances need a separate contract.')
    if re.search(r'\b(not|never|without|except|preserv\w*|keep\w*|then|and then)\b',low):
        return clarify('Specify one counterbore and its diameter and depth. Additional constraints need a separate checked contract.')
    if not selection or selection.get('region') or not selection.get('point'):
        return clarify('Click the flat top or bottom rim of an existing through-hole, then request the counterbore.')
    part=next((p for p in (state or {}).get('parts',[]) if p['id']==selection.get('part_id')),None)
    if part is None:return clarify('Select an imported part with a recognized through-hole.')
    diameter=re.search(LENGTH+r'\s*(?:diameter|wide)\b',low) or re.search(r'diameter\s*(?:of|=)?\s*'+LENGTH,low)
    depth=re.search(LENGTH+r'\s*deep\b',low) or re.search(r'depth\s*(?:of|=)?\s*'+LENGTH,low)
    tool=re.search(LENGTH+r'\s*tool\b',low)
    clearance=re.search(LENGTH+r'\s*(?:radial\s+)?clearance\b',low)
    if not depth:return clarify('Specify a finite counterbore depth, for example 2 mm deep.')
    rule=None
    consumed=[]
    if tool and clearance and not diameter:
        consumed=[tool,clearance,depth]
        if len(list(re.finditer(LENGTH,low)))!=3:return clarify('Use one tool diameter, one radial clearance and one depth.')
        from .continual import ContinualLearning,Context
        import cadquery as cq
        from . import engineering,access_experiments
        context=Context('ideal-cad-millimeters','geometric-only; unqualified',{'cadquery':cq.__version__},
            hashlib.sha256(Path(engineering.__file__).read_bytes()+Path(access_experiments.__file__).read_bytes()).hexdigest(),'tool-access-coupons-v1')
        db=Path.home()/'.local/share/cadforge/tool-access.sqlite3'
        if not db.exists():return clarify('No validated tool-pocket dimension rule is available. Specify the counterbore diameter explicitly.')
        service=ContinualLearning(db)
        try:
            inputs={'tool_diameter':_mm(*tool.groups()),'radial_clearance':_mm(*clearance.groups())}
            receipt=service.apply_with_provenance('tool_access_pocket',inputs,context=context)
            fitted=receipt['parameters'];identifier=receipt['skill_id']
            diameter_mm=fitted['pocket_diameter'];rule={'skill_id':identifier,'inputs':inputs,'output_diameter_mm':diameter_mm,
                'validator_context':context.validator_version,'dependency_ids':receipt['dependency_ids'],'scope':'Dimension initialization learned on ideal BRep coupons; imported mesh requires fresh counterbore validation.'}
        except (KeyError,ValueError):return clarify('The tool dimensions are outside a healthy learned rule. Specify an explicit counterbore diameter.')
        finally:service.close()
    elif diameter and not tool and not clearance:
        consumed=[diameter,depth]
        if len(list(re.finditer(LENGTH,low)))!=2:return clarify('Use one counterbore diameter and one depth.')
        diameter_mm=_mm(*diameter.groups())
    else:return clarify('Specify a diameter and depth, or a tool diameter, radial clearance and depth.')
    remainder=low
    for match in consumed:remainder=remainder.replace(match.group(0),' ',1)
    if set(re.findall(r"[a-z]+",remainder))-{'please','counterbore','this','the','selected','existing','hole','to','a','for','with','and','add','make','create'}:
        return clarify('This counterbore request includes unsupported instructions. Specify only the diameter and depth, or tool diameter, radial clearance and depth.')
    try:
        import numpy as np
        import trimesh
        from .protected_edit import _recognized
        point=np.asarray(selection['point'],dtype=float)
        mesh=trimesh.load(part['stl_path'],force='mesh',process=True)
        features,_=_recognized(mesh)
        matches=[f for f in features if np.linalg.norm(point[:2]-f['center'])<=f['radius_mm']+.2]
        if len(matches)!=1:return clarify('Click close to exactly one recognized circular hole rim.')
        hole=matches[0]
        if abs(point[2]-hole['z_max'])<1e-4:z=hole['z_max'];direction=-1
        elif abs(point[2]-hole['z_min'])<1e-4:z=hole['z_min'];direction=1
        else:return clarify('Click the flat top or bottom rim; a point midway down the bore does not identify an entry face.')
        command=Counterbore(op='counterbore',radius_mm=diameter_mm/2,depth_mm=_mm(*depth.groups()),entry=(*hole['center'],z),direction=direction)
    except (ValueError,KeyError):return clarify('This part does not expose a recognized circular Z-through-hole at that selection.')
    result={'command':command.model_dump(mode='json'),'clarification':None,'planner':'counterbore_parser',
        'explanation':f'Preview a {diameter_mm:g} mm diameter counterbore, {command.depth_mm:g} mm deep, centered on the recognized hole. The lower bore must remain open and unchanged.',
        'usage':{'model_requests':0,'input_tokens':0,'output_tokens':0}}
    if rule:result.update(dimension_rule=rule,learning_message='Reused a saved tool-pocket dimension rule. This imported mesh still must pass its own counterbore checks.')
    return result
