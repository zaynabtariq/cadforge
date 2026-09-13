"""Explicit prebuild supplements which cannot replace fixed hardware constraints."""
from dataclasses import replace
from math import isfinite
from .engineering import ToolAccess,Cable,Beam,assess_geometry


def supplement_contract(base,inputs):
    if not isinstance(inputs,dict):raise ValueError('Review inputs must be a dictionary')
    allowed={'tool_access','cables','beams','density_g_cm3','material_source','maximum_mass_g'}
    unknown=set(inputs)-allowed
    if unknown:raise ValueError('Review inputs cannot replace hardware requirements: '+', '.join(sorted(unknown)))
    values=dict(inputs)
    for name,kind in [('tool_access',ToolAccess),('cables',Cable),('beams',Beam)]:
        if name in values:
            if not isinstance(values[name],(tuple,list)) or any(not isinstance(x,kind) for x in values[name]):
                raise ValueError(f'{name} requires typed {kind.__name__} contracts')
            values[name]=tuple(values[name])
            names=[x.name for x in values[name]]
            if len(set(names))!=len(names) or any(not isinstance(n,str) or not n.strip() for n in names):
                raise ValueError(f'{name} requires unique nonempty names')
    for name in ('density_g_cm3','maximum_mass_g'):
        if name in values and (type(values[name]) not in (int,float) or not isfinite(values[name]) or values[name]<=0):
            raise ValueError(name+' must be positive and finite')
    if 'material_source' in values and (not isinstance(values['material_source'],str) or not values['material_source'].strip()):
        raise ValueError('Material source must be explicit and nonempty')
    if ('density_g_cm3' in values)!=('material_source' in values):
        raise ValueError('Density and its source must be supplied together')
    combined=replace(base,**values)
    # Run the evaluator's input validation before candidate construction. Its
    # absent-geometry result is deliberately ignored; it cannot qualify a part.
    assess_geometry({},combined)
    return combined
