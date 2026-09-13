from dataclasses import replace
import cadquery as cq
import pytest
from cadforge.engineering import (Envelope,Mount,Cable,Beam,EngineeringContract,
                                  assess_geometry,assess_step)


def box(x,y,z,at=(0,0,0)):
    return cq.Workplane('XY').box(x,y,z,centered=False).translate(at).val()


def status(report,name):
    return next(g.status for g in report.gates if g.name==name)


def test_component_keepout_checks_geometry_not_candidate_claim():
    contract=EngineeringContract(components=(Envelope('board',(2,2,2),(6,6,6)),))
    solid=box(10,10,10)
    report=assess_geometry({'shell':solid},contract)
    assert status(report,'component.board.placement')=='fail'
    hollow=solid.cut(box(6,6,6,(2,2,2)))
    assert status(assess_geometry({'shell':hollow},contract),'component.board.placement')=='pass'


def test_hole_requires_empty_axis_and_surrounding_bearing_material():
    contract=EngineeringContract(mounts=(Mount('M2',(5,5,0),(0,0,1),1,4,2,4),))
    solid=box(10,10,4)
    cylinder=cq.Solid.makeCylinder(1,4,cq.Vector(5,5,0))
    report=assess_geometry({'plate':solid},contract)
    assert status(report,'mount.M2.through_bore')=='fail'
    report=assess_geometry({'plate':solid.cut(cylinder)},contract)
    assert status(report,'mount.M2.through_bore')=='pass'
    assert status(report,'mount.M2.bearing_material')=='pass'
    displaced=solid.translate((100,0,0))
    report=assess_geometry({'plate':displaced},contract)
    assert status(report,'mount.M2.through_bore')=='pass'
    assert status(report,'mount.M2.bearing_material')=='fail'


def test_requested_port_corridor_and_wall_witness_measured():
    contract=EngineeringContract(ports=(Envelope('usb',(0,3,1),(10,4,2)),),wall_witnesses=(Envelope('floor',(0,0,0),(10,10,1)),))
    report=assess_geometry({'body':box(10,10,4)},contract)
    assert status(report,'port.usb.access')=='fail'
    assert status(report,'print.wall.floor')=='pass'


def test_mass_cg_and_support_load_from_actual_solid():
    contract=EngineeringContract(density_g_cm3=1,material_source='test-only synthetic density',
        maximum_mass_g=2,nose_support_mm=0,ear_support_mm=10,maximum_ear_load_n=.01,bom_complete=True)
    report=assess_geometry({'cube':box(10,10,10)},contract)
    assert report.mass_g==pytest.approx(1)
    assert report.center_of_gravity_mm==pytest.approx([5,5,5])
    assert status(report,'mass.limit')=='pass'
    assert status(report,'ergonomics.ear_load')=='pass'
    assert report.engineering_ready is False
    assert status(report,'production.release')=='blocked'


def test_no_invented_material_properties():
    report=assess_geometry({'cube':box(10,10,10)},EngineeringContract())
    assert report.mass_g is None
    assert status(report,'mass.material')=='blocked'


def test_beam_analytic_screen_requires_real_section_and_sourced_modulus():
    beam=Beam('temple',(0,0,0),(2,4,40),2,0,youngs_modulus_mpa=2000,
              modulus_source='test-only synthetic isotropic material',tip_load_n=.1,maximum_deflection_mm=2)
    report=assess_geometry({'beam':box(2,4,40)},EngineeringContract(beams=(beam,)))
    assert status(report,'beam.temple.section')=='pass'
    assert status(report,'beam.temple.deflection')=='pass'
    perforated=box(2,4,40).cut(box(2,2,10,(0,1,15)))
    report=assess_geometry({'beam':perforated},EngineeringContract(beams=(beam,)))
    assert status(report,'beam.temple.section')=='fail'
    assert status(report,'beam.temple.deflection')=='blocked'


def test_sharp_polyline_does_not_falsely_satisfy_cable_bend_radius():
    cable=Cable('ffc',((20,0,0),(20,10,0),(30,10,0)),.3,2,'test supplier requirement')
    report=assess_geometry({'body':box(5,5,5)},EngineeringContract(cables=(cable,)))
    assert status(report,'cable.ffc.clearance')=='pass'
    assert status(report,'cable.ffc.bend')=='fail'


def test_invalid_step_fails_closed(tmp_path):
    path=tmp_path/'bad.step';path.write_text('fake STEP: passed')
    report=assess_step(path,EngineeringContract())
    assert status(report,'geometry.step_import')=='fail'
    assert not report.passed


def test_disconnected_lumps_cannot_claim_one_integrated_chassis():
    disconnected=cq.Compound.makeCompound([box(2,2,2),box(2,2,2,(20,0,0))])
    report=assess_geometry({'chassis':disconnected},EngineeringContract())
    assert status(report,'geometry.valid_solids')=='fail'


def test_layout_adapter_creates_independent_world_space_mount_contract():
    from cadforge.engineering import contract_from_public_layout
    record={'source':'test fixture','component_min':[2,2,4], 'component_size':[10,5,2],
        'rotation_y':90,'origin':[100,0,30],'outer_size':[14,9,8],
        'holes':[[2,2]],'bore_diameter':2,'boss_outer_diameter':4}
    contract=contract_from_public_layout({'pi':record,'camera':record},wall_mm=1,clearance_mm=1)
    assert contract.components[0].origin==pytest.approx((104,2,18))
    assert contract.components[0].size==pytest.approx((2,5,10))
    assert contract.mounts[0].origin==pytest.approx((100,4,26))
    assert contract.mounts[0].axis==pytest.approx((1,0,0))


def test_nearly_full_hole_cannot_pass_by_using_an_undersized_probe():
    contract=EngineeringContract(mounts=(Mount('M2',(5,5,0),(0,0,1),1,4,2,4),))
    undersized=box(10,10,4).cut(cq.Solid.makeCylinder(.98,4,cq.Vector(5,5,0)))
    report=assess_geometry({'plate':undersized},contract)
    assert status(report,'mount.M2.through_bore')=='fail'


@pytest.mark.parametrize('component,declared_bore,hardware_radius', [('pi',2.0,1.25),('camera',1.8,1.0)])
def test_layout_contract_requires_real_hardware_insertion_despite_undersized_declared_bore(component,declared_bore,hardware_radius):
    from cadforge.engineering import contract_from_public_layout
    # Product layout declares a small hole, but external hardware sizes stay fixed.
    record={'source':'test fixture','component_min':[2,2,4], 'component_size':[10,5,2],
        'rotation_y':0,'origin':[0,0,0],'outer_size':[14,9,4],
        'holes':[[2,2]],'bore_diameter':declared_bore,'boss_outer_diameter':5}
    contract=contract_from_public_layout({'pi':record,'camera':record},wall_mm=1,clearance_mm=1)
    mount=next(m for m in contract.mounts if m.name==component+'_0')
    assert mount.radius_mm==hardware_radius
    plate=box(10,10,4).cut(cq.Solid.makeCylinder(declared_bore/2,4,cq.Vector(4,4,0)))
    report=assess_geometry({'plate':plate},EngineeringContract(mounts=(mount,)))
    assert status(report,'mount.'+component+'_0.through_bore')=='fail'
