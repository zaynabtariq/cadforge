"""Strict JSON contracts for agents supplying explicit engineering assumptions."""
from typing import Annotated
from pydantic import BaseModel,ConfigDict,Field,StrictFloat,StrictInt
from .engineering import ToolAccess,Cable,Beam,EngineeringContract
from .production_review import supplement_contract

Number=StrictFloat
Positive=Annotated[StrictFloat,Field(gt=0)]
Vector=tuple[Number,Number,Number]
Size=tuple[Positive,Positive,Positive]
Axis=Annotated[StrictInt,Field(ge=0,le=2)]
Text=Annotated[str,Field(min_length=1)]

class StrictInput(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False,str_strip_whitespace=True)

class ToolInput(StrictInput):
    name:Text
    origin:Vector
    axis:Vector
    radius_mm:Positive
    length_mm:Positive
    source:Text

class CableInput(StrictInput):
    name:Text
    centerline:Annotated[list[Vector],Field(min_length=2)]
    radius_mm:Positive
    minimum_bend_radius_mm:Positive|None=None
    source:Text|None=None

class BeamInput(StrictInput):
    name:Text
    origin:Vector
    size:Size
    length_axis:Axis
    bending_axis:Axis
    youngs_modulus_mpa:Positive|None=None
    modulus_source:Text|None=None
    tip_load_n:Annotated[StrictFloat,Field(ge=0)]|None=None
    maximum_deflection_mm:Positive=2.0

class ReviewInput(StrictInput):
    tool_access:list[ToolInput]=Field(default_factory=list)
    cables:list[CableInput]=Field(default_factory=list)
    beams:list[BeamInput]=Field(default_factory=list)
    density_g_cm3:Positive|None=None
    material_source:Text|None=None
    maximum_mass_g:Positive|None=None

    def contracts(self):
        values=self.model_dump(exclude_unset=True)
        for name,kind in [('tool_access',ToolAccess),('cables',Cable),('beams',Beam)]:
            if name in values:values[name]=tuple(kind(**row) for row in values[name])
        # Same boundary validation as Python callers, before any CAD is built.
        supplement_contract(EngineeringContract(),values)
        return values
