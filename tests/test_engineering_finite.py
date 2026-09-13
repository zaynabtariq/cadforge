"""Independent finite engineering-contract and computed-result regressions."""
from dataclasses import replace
import json
import cadquery as cq
import pytest
from cadforge.engineering import EngineeringContract, Envelope, assess_geometry

BASE = EngineeringContract(density_g_cm3=1.,material_source='nominal assumption',maximum_mass_g=100.,
                           nose_support_mm=-10.,ear_support_mm=10.,maximum_ear_load_n=1.,bom_complete=True)


class UnmeasurableShape:
    def isValid(self):raise AssertionError('Contract must be rejected before geometry measurement')
    def Volume(self):raise AssertionError('Contract must be rejected before geometry measurement')


@pytest.mark.parametrize('field', ['density_g_cm3','maximum_mass_g','nose_support_mm','ear_support_mm','maximum_ear_load_n'])
@pytest.mark.parametrize('value',[float('nan'),float('inf'),-float('inf')])
def test_nonfinite_contract_rejected_before_geometry_measurement(field,value):
    contract = replace(BASE,**{field:value})
    with pytest.raises(ValueError):assess_geometry({'stock':UnmeasurableShape()},contract)


@pytest.mark.parametrize('value',[float('nan'),float('inf'),-float('inf')])
def test_nonfinite_component_mass_rejected_before_geometry_measurement(value):
    component = Envelope('external',(20.,20.,20.),(1.,1.,1.),mass_g=value)
    contract = replace(BASE,components=(component,))
    with pytest.raises(ValueError):assess_geometry({'stock':UnmeasurableShape()},contract)


@pytest.mark.parametrize('axis',[-1,3])
def test_invalid_support_axis_rejected_before_geometry_measurement(axis):
    with pytest.raises(ValueError):
        assess_geometry({'stock':UnmeasurableShape()},replace(BASE,support_axis=axis))


def test_finite_input_overflow_rejected_with_controlled_value_error():
    stock = cq.Workplane('XY').box(10,10,10).val()
    with pytest.raises(ValueError):
        assess_geometry({'stock':stock},replace(BASE,density_g_cm3=1e308))


def test_valid_nominal_contract_measures_one_gram_and_serializes_finite_json():
    stock = cq.Workplane('XY').box(10,10,10).val()
    result = assess_geometry({'stock':stock},BASE)
    assert result.mass_g == pytest.approx(1.)
    assert result.center_of_gravity_mm == pytest.approx([0.,0.,0.],abs=1e-12)
    gates = {gate.name:gate for gate in result.gates}
    assert gates['mass.limit'].status == 'pass'
    assert gates['ergonomics.ear_load'].status == 'pass'
    assert gates['ergonomics.ear_load'].measured == pytest.approx(.004903325)
    json.dumps(result.model_dump(),allow_nan=False)
    assert not result.engineering_ready
