"""Reusable post-composition interface repair learned from measured interference.

The developer observed 0.088588 mm3 of cable-guide material in a nominal camera
bore. Callers supply protected voids and occupied-material witnesses externally;
this command never moves their axes or relaxes their dimensions.
"""
from dataclasses import dataclass
import cadquery as cq

@dataclass(frozen=True)
class InterfaceRepair:
    shape: cq.Shape
    removed_volume_mm3: float
    protected_void_count: int
    protected_material_count: int


def preserve_interface_voids(shape, voids, required_material=(), *, require_single=True, tolerance=1e-6):
    """Subtract accidental fills after unions; fail without mutating the input.

    Single-solid preservation is the default. Multi-part routing assemblies may
    explicitly allow multiple solids, which must subsequently be named/exported
    separately. Witness preservation is exact occupied volume, not a strength claim.
    """
    voids=tuple(voids);required_material=tuple(required_material)
    if not shape.isValid() or not shape.Solids():
        raise ValueError('Input must contain valid solid material')
    repaired=shape
    for void in voids:
        if not void.isValid() or void.Volume()<=0:
            raise ValueError('Protected void must have positive valid volume')
        repaired=repaired.cut(void)
    if not repaired.isValid() or not repaired.Solids() or (require_single and len(repaired.Solids())!=1):
        raise ValueError('Repair would remove or disconnect required body; original retained')
    for void in voids:
        if repaired.intersect(void).Volume()>tolerance:
            raise ValueError('Protected interface remains blocked; original retained')
    for witness in required_material:
        if abs(repaired.intersect(witness).Volume()-witness.Volume())>tolerance:
            raise ValueError('Repair would remove required bearing material; original retained')
    return InterfaceRepair(repaired,shape.Volume()-repaired.Volume(),len(voids),len(required_material))


def translation_for_anchor(local_anchor, target_anchor):
    """Solve a rigid translation from a component mating anchor to its target.

    Inputs must already use the same axis orientation. Unlike a saved world
    offset, this constraint remains valid when either component changes size.
    """
    import math
    if len(local_anchor)!=3 or len(target_anchor)!=3:
        raise ValueError('Mating anchors must be three-dimensional')
    if not all(math.isfinite(float(v)) for v in (*local_anchor,*target_anchor)):
        raise ValueError('Mating anchors must be finite')
    return tuple(float(target)-float(local) for local,target in zip(local_anchor,target_anchor))
