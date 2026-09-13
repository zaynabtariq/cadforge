import pytest
from cadforge.geometry import box, cylinder
from cadforge.operations import preserve_interface_voids


def test_robot_link_composition_restores_original_pivot_axis():
    pivot=cylinder(2.5,8,(8,8,-1))
    link=box(40,16,6).cut(pivot)
    # A later reinforcement union accidentally fills the protected pivot.
    reinforced=link.fuse(box(16,16,2))
    bearing=cylinder(5,6,(8,8,0)).cut(cylinder(2.5,6,(8,8,0)))
    repaired=preserve_interface_voids(reinforced,[pivot],[bearing])
    assert repaired.removed_volume_mm3>0
    assert repaired.shape.intersect(pivot).Volume()<1e-6
    assert reinforced.intersect(pivot).Volume()>0  # input is unchanged
    assert len(repaired.shape.Solids())==1
    assert repaired.shape.BoundingBox().xlen==pytest.approx(40)


def test_repair_rolls_back_if_it_would_disconnect_body():
    body=box(20,4,4)
    with pytest.raises(ValueError,match='disconnect'):
        preserve_interface_voids(body,[box(2,6,6,(9,-1,-1))])
    assert len(body.Solids())==1


def test_repair_cannot_sacrifice_required_bearing_material():
    body=box(20,20,5);void=cylinder(4,7,(10,10,-1))
    protected=cylinder(2,5,(10,10,0))
    with pytest.raises(ValueError,match='bearing'):
        preserve_interface_voids(body,[void],[protected])


def test_mating_anchor_translation_preserves_target_after_resize():
    from cadforge.operations import translation_for_anchor
    for size in (30,35,44):
        offset=translation_for_anchor((0,size,0),(130,44.4,87))
        assert tuple(a+b for a,b in zip(offset,(0,size,0)))==pytest.approx((130,44.4,87))
