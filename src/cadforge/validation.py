"""BRep checks. This is not a mechanics or manufacturing certification."""
from itertools import combinations
from .geometry import BuildResult
from .schema import CheckResult, ValidationReport


def validate_design(result: BuildResult) -> ValidationReport:
    checks = []
    measurements = {}
    def check(name, passed, actual=None, expected=None, detail=''):
        checks.append(CheckResult(name=name,passed=bool(passed),actual=actual,expected=expected,detail=detail))
    p = result.spec.resolved()
    check('named_parts', bool(result.parts), len(result.parts), '>=1')
    for name, shape in result.parts.items():
        volume = shape.Volume()
        measurements[f'{name}_volume_mm3'] = volume
        check(f'valid_solid_{name}', shape.isValid() and len(shape.Solids()) == 1, len(shape.Solids()), 1)
        check(f'positive_volume_{name}', volume > 1e-6, volume, '>0')
        bb=shape.BoundingBox()
        for axis in 'xyz':
            measurements[f'{name}_{axis}_mm'] = getattr(bb,axis+'len')
    for (n,a),(m,b) in combinations(result.parts.items(),2):
        intersection = a.intersect(b).Volume()
        check(f'noncollision_{n}_{m}', intersection < 1e-6, intersection, '<1e-6 mm3')
    for name, probe in result.probes.items():
        if name.endswith('_wall'):
            material = sum(s.intersect(probe).Volume() for s in result.parts.values())
            check(name, abs(material-probe.Volume()) < 1e-5, material, probe.Volume())
            # The section witness is measured from the manufactured BRep, not solely IR.
            witnesses = [s.intersect(probe) for s in result.parts.values() if s.intersect(probe).Volume()>1e-8]
            thickness = max((s.BoundingBox().zlen for s in witnesses), default=0.0)
            measurements['measured_wall_mm'] = thickness
            check('minimum_wall', thickness >= 1.2-1e-6, thickness, '>=1.2 mm')
        else:
            overlap = sum(s.intersect(probe).Volume() for s in result.parts.values())
            check(name, overlap < 1e-6, overlap, '<1e-6 mm3')
            if name == 'component_clearance':
                distance = result.parts['housing'].distance(probe)
                measurements['component_clearance_mm'] = distance
                check('minimum_component_clearance', distance >= .2-1e-6, distance, '>=0.2 mm')
    # Reject missing probes and parts so a bare valid box cannot pass the contract.
    family = result.spec.family
    required = {'glasses': {'housing','lid','frame'},'enclosure':{'housing','lid'},'bracket':{'bracket'},'clip':{'clip'}}[family]
    check('required_parts', required <= result.parts.keys(), ','.join(sorted(result.parts)), ','.join(sorted(required)))
    required_probes = {'glasses':{'component_clearance','camera_aperture','floor_wall','lens_left_aperture','lens_right_aperture'},'enclosure':{'component_clearance','camera_aperture','floor_wall'},'bracket':{'mount_aperture','base_wall'},'clip':{'clip_gap','base_wall'}}[family]
    check('required_probes',required_probes <= result.probes.keys())
    if family in ('glasses','enclosure') and 'housing' in result.parts:
        bb=result.parts['housing'].BoundingBox()
        for axis,key in [('x','board_length'),('y','board_width')]:
            actual=getattr(bb,axis+'len')
            expected=p[key]+2*p['clearance']+2*p['wall']
            if family == 'enclosure' and axis == 'x':
                expected += p['screw_diameter']+2*p['wall']
            check(f'housing_{axis}_dimension',abs(actual-expected)<1e-5,actual,expected)
        expected_z=p['board_height']+p['clearance']+p['wall']
        check('housing_z_dimension',abs(bb.zlen-expected_z)<1e-5,bb.zlen,expected_z)
        if family == 'glasses' and 'frame' in result.parts:
            frame_bb=result.parts['frame'].BoundingBox()
            expected_frame={'x':2*(p['lens_width']+2*p['wall'])+p['bridge'], 'y':p['lens_height']+2*p['wall'], 'z':max(p['temple_length'],p['wall'])}
            for axis, expected in expected_frame.items():
                check(f'frame_{axis}_dimension',abs(getattr(frame_bb,axis+'len')-expected)<1e-5,getattr(frame_bb,axis+'len'),expected)
    elif family == 'bracket' and 'bracket' in result.parts:
        bb=result.parts['bracket'].BoundingBox()
        for axis,key in [('x','width'),('y','depth'),('z','height')]:
            check(f'bracket_{axis}_dimension',abs(getattr(bb,axis+'len')-p[key])<1e-5,getattr(bb,axis+'len'),p[key])
    elif family == 'clip' and 'clip' in result.parts:
        bb=result.parts['clip'].BoundingBox()
        for axis,expected in [('x',p['width']),('y',p['gap']+2*p['wall']),('z',p['height'])]:
            check(f'clip_{axis}_dimension',abs(getattr(bb,axis+'len')-expected)<1e-5,getattr(bb,axis+'len'),expected)
    result.measurements.update(measurements)
    report = ValidationReport(passed=all(c.passed for c in checks),checks=checks,measurements=measurements)
    if family == 'enclosure':
        report.limitations = [
            'External mounting bores are modeled; threads, fastener engagement, ventilation and operational assembly readiness remain unresolved.'
            if text.startswith('Screw diameter is reserved') else
            'Lid has aligned clearance holes but is separated by clearance; fastener hardware and preload remain unverified.'
            if text.startswith('Lid is separated') else text
            for text in report.limitations
        ]
    return report
