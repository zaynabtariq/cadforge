"""Editable millimetre-based CAD intermediate representation."""
from typing import Literal
import math
from pydantic import BaseModel, Field, field_validator

DEFAULTS = dict(wall=2.0, clearance=0.6, board_length=65.0, board_width=30.0,
    board_height=6.0, camera_diameter=8.0, lid_thickness=2.0, screw_diameter=2.5,
    lens_width=48.0, lens_height=34.0, bridge=18.0, temple_length=140.0,
    width=40.0, height=40.0, depth=30.0, hole_diameter=5.0, gap=8.0)

class DesignSpec(BaseModel):
    """Numbers are mm; component envelopes are assumptions, not vendor certification."""
    family: Literal['glasses', 'enclosure', 'bracket', 'clip']
    parameters: dict[str, float] = Field(default_factory=dict)
    name: str = 'design'

    @field_validator('parameters')
    @classmethod
    def finite_parameters(cls, value):
        for key, number in value.items():
            if not math.isfinite(number):
                raise ValueError(f'{key} must be finite')
            if abs(number) > 2000:
                raise ValueError(f'{key} exceeds 2000 mm resource limit')
        return value

    def resolved(self) -> dict[str, float]:
        return DEFAULTS | self.parameters

class CheckResult(BaseModel):
    name: str
    passed: bool
    actual: float | str | bool | None = None
    expected: float | str | bool | None = None
    detail: str = ''

class ValidationReport(BaseModel):
    passed: bool
    checks: list[CheckResult]
    measurements: dict[str, float] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=lambda: [
        'Geometry checks only; no FEA, fatigue, thermal, electrical, optical or wearability certification.',
        'Pi dimensions are configurable envelope assumptions, not a sourced component model.',
        'Camera aperture only: no camera module envelope, retention, lens alignment, or cable routing has been verified.',
        'Lid is separated by clearance and has no fastening features; glasses housing touches temple without a verified mechanical joint.',
        'Screw diameter is reserved but screw holes and ventilation are not implemented; operational assembly readiness is unresolved.'
    ])
