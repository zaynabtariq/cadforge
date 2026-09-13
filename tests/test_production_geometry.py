from itertools import combinations
import pytest
from cadforge.schema import DesignSpec
from cadforge.production_geometry import build_design, layout, export_design


def test_source_grounded_pattern_and_temple_orientation():
    data=layout(DesignSpec(family='glasses'))
    assert data['pi']['board_size']==[65,30]
    assert data['pi']['holes']==[[3.5,3.5],[61.5,3.5],[3.5,26.5],[61.5,26.5]]
    assert data['camera']['holes']==[[2,2],[23,2],[2,14.5],[23,14.5]]
    assert data['pi']['rotation_y']==90


def test_production_brep_interfaces_and_export(tmp_path):
    b=build_design(DesignSpec(family='glasses'))
    for name,shape in b.parts.items():
        assert shape.isValid() and len(shape.Solids())==1,name
    for (n,a),(m,c) in combinations(b.parts.items(),2):
        assert a.intersect(c).Volume()<1e-5,(n,m)
    for name,probe in b.probes.items():
        if 'floor_wall' not in name:
            assert sum(s.intersect(probe).Volume() for s in b.parts.values())<1e-5,name
    assert len(b.probes['cable_channel'].Solids())==1
    assert b.probes['cable_channel'].intersect(b.probes['port_csi']).Volume()>0
    assert b.probes['cable_channel'].intersect(b.probes['camera_ribbon_port']).Volume()>0
    paths=export_design(b,tmp_path)
    assert 'production_geometry' in (tmp_path/'design.py').read_text()
    assert (tmp_path/'hardware_layout.json').exists()


def test_learned_bore_parameter_changes_actual_geometry():
    a=build_design(DesignSpec(family='glasses',parameters={'bore_diameter':2.6}))
    b=build_design(DesignSpec(family='glasses',parameters={'bore_diameter':2.9}))
    assert b.probes['pi_mount_hole_0'].Volume()>a.probes['pi_mount_hole_0'].Volume()
    assert abs(a.parts['chassis'].Volume()-b.parts['chassis'].Volume())>1


def test_independent_full_bore_gate_rejects_ring_intrusions():
    from cadforge.engineering import contract_from_public_layout, assess_geometry
    b=build_design(DesignSpec(family='glasses'))
    contract=contract_from_public_layout(layout(b.spec),wall_mm=2,clearance_mm=.6)
    report=assess_geometry(b.parts,contract)
    assert not [g for g in report.gates if g.status=='fail']
    assert any(g.status=='blocked' for g in report.gates)  # physical evidence remains absent


@pytest.mark.parametrize('width',[48,52,54])
@pytest.mark.parametrize('height',[34,42.4,46])
@pytest.mark.parametrize('temple',[140,145,150])
def test_mating_layout_transfers_across_frame_dimensions(width,height,temple):
    spec=DesignSpec(family='glasses',parameters={'lens_width':width,'lens_height':height,'temple_length':temple,'wall':2,'clearance':.5,'bore_diameter':2.8,'boss_outer_diameter':5.8})
    b=build_design(spec)
    assert len(b.parts['chassis'].Solids())==1
    for name,probe in b.probes.items():
        if 'floor_wall' not in name:
            assert sum(s.intersect(probe).Volume() for s in b.parts.values())<1e-5,name
    assert b.probes['cable_channel'].intersect(b.probes['port_csi']).Volume()>0
    assert b.probes['cable_channel'].intersect(b.probes['camera_ribbon_port']).Volume()>0
    data=layout(spec)
    assert data['pi']['origin'][1]+data['pi']['outer_size'][1]==pytest.approx(height+2)
