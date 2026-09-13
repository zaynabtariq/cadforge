"""Independent, evidence-graded engineering gates on delivered BRep geometry.

Contracts must be supplied by the evaluator/product owner, never synthesized from
candidate measurements. Passing numerical gates is not production certification.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from itertools import combinations
from math import isfinite, sqrt, hypot
from pathlib import Path
from typing import Literal
import cadquery as cq

Status = Literal['pass','fail','blocked']
Vec3 = tuple[float,float,float]

@dataclass(frozen=True)
class Gate:
    name: str
    status: Status
    detail: str
    measured: float | list[float] | None = None
    limit: float | None = None

@dataclass(frozen=True)
class Envelope:
    name: str
    origin: Vec3
    size: Vec3
    clearance_mm: float = 0.0
    mass_g: float | None = None
    source: str = 'Unverified assembly envelope assumption'

@dataclass(frozen=True)
class Mount:
    name: str
    origin: Vec3
    axis: Vec3
    radius_mm: float
    length_mm: float
    support_radius_mm: float
    support_length_mm: float

@dataclass(frozen=True)
class Cable:
    name: str
    centerline: tuple[Vec3,...]
    radius_mm: float
    minimum_bend_radius_mm: float | None = None
    source: str | None = None

@dataclass(frozen=True)
class ToolAccess:
    name: str
    origin: Vec3
    axis: Vec3
    radius_mm: float
    length_mm: float
    source: str

@dataclass(frozen=True)
class Beam:
    name: str
    origin: Vec3
    size: Vec3
    length_axis: int
    bending_axis: int
    youngs_modulus_mpa: float | None = None
    modulus_source: str | None = None
    tip_load_n: float | None = None
    maximum_deflection_mm: float = 2.0

@dataclass(frozen=True)
class EngineeringContract:
    components: tuple[Envelope,...] = ()
    ports: tuple[Envelope,...] = ()
    mounts: tuple[Mount,...] = ()
    cables: tuple[Cable,...] = ()
    wall_witnesses: tuple[Envelope,...] = ()
    beams: tuple[Beam,...] = ()
    density_g_cm3: float | None = None
    material_source: str | None = None
    maximum_mass_g: float | None = None
    support_axis: int = 2
    nose_support_mm: float | None = None
    ear_support_mm: float | None = None
    maximum_ear_load_n: float | None = None
    bom_complete: bool = False
    required_parts: tuple[str,...] = ()
    physical_evidence: dict[str,str] = field(default_factory=dict)
    tool_access: tuple[ToolAccess,...] = ()

@dataclass
class EngineeringReport:
    gates: list[Gate]
    mass_g: float | None = None
    center_of_gravity_mm: list[float] | None = None

    @property
    def passed(self):
        return bool(self.gates) and all(g.status=='pass' for g in self.gates)

    @property
    def engineering_ready(self):
        # Physical release is outside this automated evaluator's authority.
        return False

    def model_dump(self):
        return {'gates':[asdict(g) for g in self.gates], 'mass_g':self.mass_g,
                'center_of_gravity_mm':self.center_of_gravity_mm,
                'passed':self.passed,'engineering_ready':False,
                'counts':{s:sum(g.status==s for g in self.gates) for s in ('pass','fail','blocked')}}


def _box(e: Envelope, grow=0.0):
    if any(not isfinite(v) or v<=0 for v in e.size) or grow<0:
        raise ValueError('Envelope dimensions must be finite and positive')
    return cq.Workplane('XY').box(*(v+2*grow for v in e.size), centered=False).translate(tuple(v-grow for v in e.origin)).val()


def _cylinder(origin, axis, radius, length):
    if radius<=0 or length<=0 or not all(isfinite(v) for v in (*origin,*axis,radius,length)):
        raise ValueError('Invalid cylindrical witness')
    return cq.Solid.makeCylinder(radius,length,cq.Vector(*origin),cq.Vector(*axis))


def _distance(a,b):
    return sqrt(sum((x-y)**2 for x,y in zip(a,b)))


def assess_geometry(parts: dict[str,cq.Shape], contract: EngineeringContract) -> EngineeringReport:
    """Measure candidate solids against independently supplied assembly contracts."""
    # External engineering contracts are data, not validated merely because
    # they were constructed as dataclasses. Reject nonfinite inputs before CAD
    # work: infinite support spans otherwise produce a false zero-load pass.
    def finite_data(value,path='contract'):
        if isinstance(value,dict):
            for key,item in value.items():finite_data(item,f'{path}.{key}')
        elif isinstance(value,(list,tuple)):
            for i,item in enumerate(value):finite_data(item,f'{path}[{i}]')
        elif isinstance(value,(int,float)) and not isinstance(value,bool):
            try:finite=isfinite(value)
            except OverflowError:finite=False
            if not finite:raise ValueError(f'{path} must be finite')
    finite_data(asdict(contract))
    if type(contract.support_axis) is not int or contract.support_axis not in (0,1,2):
        raise ValueError('Support axis must be 0, 1 or 2')
    for beam in contract.beams:
        if any(type(axis) is not int for axis in (beam.length_axis,beam.bending_axis)):
            raise ValueError('Beam axes must be integers')
    for access in contract.tool_access:
        if (len(access.origin)!=3 or len(access.axis)!=3 or hypot(*access.axis)<=0
                or isinstance(access.radius_mm,bool) or isinstance(access.length_mm,bool)
                or access.radius_mm<=0 or access.length_mm<=0 or not access.source.strip()):
            raise ValueError('Tool access requires finite vectors, a nonzero axis, positive dimensions and an explicit source')
    for cable in contract.cables:
        for name,value in (('radius_mm',cable.radius_mm),('minimum_bend_radius_mm',cable.minimum_bend_radius_mm)):
            if name=='minimum_bend_radius_mm' and value is None:continue
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not isfinite(value) or value<=0:
                raise ValueError(f'Cable {name} must be positive and finite')
        for point in cable.centerline:
            if not isinstance(point,(tuple,list)) or len(point)!=3 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v) for v in point):
                raise ValueError('Cable centerline points must have three finite coordinates')
        for a,b in zip(cable.centerline,cable.centerline[1:]):
            length=hypot(*(y-x for x,y in zip(a,b)))
            if not isfinite(length) or length<=0:
                raise ValueError('Cable centerline segments must have positive finite length')
    gates=[]
    def add(name, good, detail, measured=None, limit=None):
        finite_data({'measured':measured,'limit':limit},f'gate.{name}')
        gates.append(Gate(name,'pass' if good else 'fail',detail,measured,limit))
    def blocked(name, detail):
        gates.append(Gate(name,'blocked',detail))
    valid = bool(parts) and all(s.isValid() and s.Volume()>1e-8 and len(s.Solids())==1 for s in parts.values())
    add('geometry.valid_solids',valid,'Each named part must be one valid connected solid with positive material volume')
    add('geometry.required_parts',set(contract.required_parts)<=parts.keys(),'Externally required named parts')
    if not valid:
        blocked('engineering.remaining','Invalid or absent geometry prevents physical measurements')
        return EngineeringReport(gates)
    material=cq.Compound.makeCompound(list(parts.values()))
    tol=1e-5
    for (an,a),(bn,b) in combinations(parts.items(),2):
        volume=a.intersect(b).Volume()
        add(f'geometry.noncollision.{an}.{bn}',volume<tol,'Part material may touch but must not interpenetrate',volume,tol)
    for e in contract.components:
        occupied=material.intersect(_box(e,e.clearance_mm)).Volume()
        add(f'component.{e.name}.placement',occupied<tol,f'External component keepout including clearance; source: {e.source}',occupied,tol)
    if not contract.components:
        blocked('component.placement','No external component placement contract supplied')
    for port in contract.ports:
        occupied=material.intersect(_box(port,port.clearance_mm)).Volume()
        add(f'port.{port.name}.access',occupied<tol,'Specified connector insertion corridor is clear; connector force untested',occupied,tol)
    if not contract.ports:
        blocked('port.access','No externally specified connector insertion corridors')
    for mount in contract.mounts:
        bore=_cylinder(mount.origin,mount.axis,mount.radius_mm*.999,mount.length_mm)
        support=_cylinder(mount.origin,mount.axis,mount.support_radius_mm,mount.support_length_mm).cut(_cylinder(mount.origin,mount.axis,mount.radius_mm*1.001,mount.support_length_mm))
        occupied=material.intersect(bore).Volume()
        available=material.intersect(support).Volume()
        add(f'mount.{mount.name}.through_bore',occupied<tol,'Material-free cylinder at prescribed fastener axis',occupied,tol)
        add(f'mount.{mount.name}.bearing_material',support.Volume()>tol and abs(available-support.Volume())<tol,'A clear hole also requires the specified surrounding bearing annulus',available,support.Volume())
    if not contract.mounts:
        blocked('assembly.mounts','No independently positioned fastener axes and bearing annuli supplied')
    for access in contract.tool_access:
        witness=_cylinder(access.origin,access.axis,access.radius_mm,access.length_mm)
        occupied=material.intersect(witness).Volume()
        add(f'assembly.tool_access.{access.name}',occupied<tol,
            'Straight cylindrical tool corridor against printed parts only; excludes purchased hardware and tool turning motion. Source: '+access.source,
            occupied,tol)
    if not contract.tool_access:
        blocked('assembly.tool_access','Tool dimensions, approach directions and assembly access corridors are unspecified')
    for wall in contract.wall_witnesses:
        witness=_box(wall)
        volume=material.intersect(witness).Volume()
        add(f'print.wall.{wall.name}',abs(volume-witness.Volume())<tol,'Local full-thickness material witness; does not establish global minimum wall',volume,witness.Volume())
    if not contract.wall_witnesses:
        blocked('print.wall','No independent minimum-wall witness locations')
    for cable in contract.cables:
        if len(cable.centerline)<2:
            add(f'cable.{cable.name}.route',False,'Route needs at least two independently specified points')
            continue
        route_clear=True
        for a,b in zip(cable.centerline,cable.centerline[1:]):
            length=_distance(a,b)
            if length<=0:
                route_clear=False
                continue
            swept=_cylinder(a,tuple(y-x for x,y in zip(a,b)),cable.radius_mm,length)
            for point in (a,b):
                swept=swept.fuse(cq.Solid.makeSphere(cable.radius_mm,cq.Vector(*point),angleDegrees1=-90))
            route_clear &= material.intersect(swept).Volume()<tol
        add(f'cable.{cable.name}.clearance',route_clear,'Conservative swept circular cable envelope along supplied polyline')
        if cable.minimum_bend_radius_mm is None or not cable.source:
            blocked(f'cable.{cable.name}.bend','Cable supplier bend-radius limit/source missing')
        elif len(cable.centerline)==2:
            add(f'cable.{cable.name}.bend',True,'Straight segment has no bend; endpoint connector strain remains unverified')
        else:
            # A polyline has sharp corners, irrespective of circumcircle through samples.
            straight=True
            for a,b,c in zip(cable.centerline,cable.centerline[1:],cable.centerline[2:]):
                ab,bc=tuple(y-x for x,y in zip(a,b)),tuple(y-x for x,y in zip(b,c))
                ab_length,bc_length=hypot(*ab),hypot(*bc)
                ab,bc=tuple(v/ab_length for v in ab),tuple(v/bc_length for v in bc)
                cross=(ab[1]*bc[2]-ab[2]*bc[1],ab[2]*bc[0]-ab[0]*bc[2],ab[0]*bc[1]-ab[1]*bc[0])
                straight &= hypot(*cross)<=1e-12 and sum(x*y for x,y in zip(ab,bc))>0
            add(f'cable.{cable.name}.bend',straight,'Polyline corners have zero radius; straightness uses normalized directions with sine-angle tolerance 1e-12. Curved routes require independently verified arc geometry')
    if not contract.cables:
        blocked('cable.routing','Cable route, connector termination and bend specifications missing')
    mass=None;cg=None
    if contract.density_g_cm3 is None or contract.density_g_cm3<=0 or not contract.material_source:
        blocked('mass.material','Material density and source required; no implicit PLA properties')
    elif any(e.mass_g is None or e.mass_g<0 for e in contract.components):
        blocked('mass.components','Actual component mass inputs are incomplete')
    else:
        weighted=[]
        for shape in parts.values():
            m=shape.Volume()*contract.density_g_cm3/1000
            if not isfinite(m) or m<=0:
                raise ValueError('Computed material mass must be finite and positive')
            center=shape.Center()
            weighted.append((m,(center.x,center.y,center.z)))
        weighted.extend((e.mass_g,tuple(a+b/2 for a,b in zip(e.origin,e.size))) for e in contract.components)
        mass=sum(m for m,_ in weighted)
        cg=[sum(m*p[i] for m,p in weighted)/mass for i in range(3)] if mass>0 else None
        finite_data({'mass_g':mass,'center_of_gravity_mm':cg},'computed')
        if contract.maximum_mass_g is None:
            blocked('mass.limit','No product mass requirement supplied')
        else:
            add('mass.limit',mass<=contract.maximum_mass_g,'BRep solid material plus supplied component masses; no infill mass assumption',mass,contract.maximum_mass_g)
        if not contract.bom_complete:
            blocked('mass.bom_completeness','Fasteners, wiring, battery and all installed hardware must be inventoried')
        if None in (contract.nose_support_mm,contract.ear_support_mm,contract.maximum_ear_load_n) or cg is None:
            blocked('ergonomics.ear_load','Support positions and load requirement missing')
        else:
            span=contract.ear_support_mm-contract.nose_support_mm
            finite_data(span,'computed.support_span_mm')
            if abs(span)<1e-9:
                add('ergonomics.ear_load',False,'Nose and ear support locations coincide')
            else:
                fraction=(cg[contract.support_axis]-contract.nose_support_mm)/span
                reaction=mass/1000*9.80665*fraction
                finite_data({'support_fraction':fraction,'reaction_n':reaction},'computed')
                add('ergonomics.static_support',0<=fraction<=1,'Two-support static model requires CG between supports',fraction,1)
                add('ergonomics.ear_load',0<=reaction<=contract.maximum_ear_load_n,'Total ear reaction in two-support static model, not contact pressure or comfort',reaction,contract.maximum_ear_load_n)
    for beam in contract.beams:
        if beam.length_axis==beam.bending_axis or any(i not in (0,1,2) for i in (beam.length_axis,beam.bending_axis)):
            add(f'beam.{beam.name}.section',False,'Invalid beam axes')
            continue
        witness=_box(Envelope(beam.name,beam.origin,beam.size))
        full=abs(material.intersect(witness).Volume()-witness.Volume())<tol
        add(f'beam.{beam.name}.section',full,'The complete externally specified rectangular beam prism must contain material')
        if beam.youngs_modulus_mpa is None or beam.youngs_modulus_mpa<=0 or not beam.modulus_source or beam.tip_load_n is None or beam.tip_load_n<0:
            blocked(f'beam.{beam.name}.deflection','Sourced effective printed modulus and externally specified tip load required')
        elif not full:
            blocked(f'beam.{beam.name}.deflection','Rectangular-beam model invalid for missing or perforated section')
        else:
            length=beam.size[beam.length_axis];h=beam.size[beam.bending_axis]
            width=beam.size[3-beam.length_axis-beam.bending_axis]
            inertia=width*h**3/12
            deflection=beam.tip_load_n*length**3/(3*beam.youngs_modulus_mpa*inertia)
            finite_data(deflection,'computed.deflection_mm')
            add(f'beam.{beam.name}.deflection',deflection<=beam.maximum_deflection_mm and deflection/length<.05,'Linear Euler-Bernoulli tip-load screening; also require <5% length small-deflection assumption. Not FEA.',deflection,beam.maximum_deflection_mm)
    if not contract.beams:
        blocked('beam.deflection','No independently measured beam section, load case and sourced modulus')
    for name,reason in {
        'print.global_wall':'Local witnesses are insufficient for a global thickness proof.',
        'print.overhang':'Requires chosen print orientation, layer process and actual slicer/support validation.',
        'material.process':'Requires material lot, anisotropy/creep properties and qualified manufacturing process.',
        'assembly.fastener_strength':'Hole geometry does not establish screw engagement, torque, pullout or fatigue strength.',
        'manufacturing.tolerance':'Requires measured printer capability and fit/assembly trials.',
        'thermal.electronics':'Requires powered assembly measurements and component limits.',
        'ergonomics.wear_trial':'Mass/statics cannot establish skin safety, fit or prolonged wear comfort.',
        'production.release':'Physical prototype, independent review and documented acceptance evidence required.'}.items():
        supplied=contract.physical_evidence.get(name)
        blocked(name,reason+(' External evidence reference supplied but not authenticated by this evaluator: '+supplied if supplied else ''))
    return EngineeringReport(gates,mass,cg)


def assess_step(path: str | Path, contract: EngineeringContract) -> EngineeringReport:
    """Import the delivered file; never regenerate an ideal candidate from its claims."""
    try:
        imported=cq.importers.importStep(str(path)).val()
        parts={f'solid_{i}':shape for i,shape in enumerate(imported.Solids())}
        if contract.required_parts:
            # STEP solid order does not prove semantic part identities.
            return EngineeringReport([Gate('geometry.part_identity','blocked','Named part identity unavailable through anonymous STEP import; use independently mapped parts')])
        return assess_geometry(parts,contract)
    except Exception as exc:
        return EngineeringReport([Gate('geometry.step_import','fail',f'Import/measurement failed: {type(exc).__name__}')])


def contract_from_public_layout(layout: dict, *, wall_mm: float, clearance_mm: float,
                                density_g_cm3: float | None = None,
                                material_source: str | None = None) -> EngineeringContract:
    """Convenience adapter for an evaluator-approved, pre-build layout contract.

    Persist/hash the input before generating candidates. Never pass a candidate's
    exported hardware_layout.json as independent evidence. Component heights and
    connector boxes in this layout remain provisional assembly assumptions.
    """
    from math import cos,sin,radians
    components=[];mounts=[];walls=[];ports=[]
    def point(p,record):
        angle=radians(record['rotation_y']);x,y,z=p
        return (x*cos(angle)+z*sin(angle)+record['origin'][0],y+record['origin'][1],-x*sin(angle)+z*cos(angle)+record['origin'][2])
    def envelope(name,origin,size,record,source='Provisional product contract'):
        corners=[point((origin[0]+i*size[0],origin[1]+j*size[1],origin[2]+k*size[2]),record) for i in (0,1) for j in (0,1) for k in (0,1)]
        minimum=tuple(min(p[a] for p in corners) for a in (0,1,2))
        extent=tuple(max(p[a] for p in corners)-minimum[a] for a in (0,1,2))
        return Envelope(name,minimum,extent,source=source)
    for name in ('pi','camera'):
        record=layout[name];ox,oy,oz=record['outer_size']
        components.append(envelope(name,record['component_min'],record['component_size'],record,record['source']+'; populated envelope height remains an assumption'))
        angle=radians(record['rotation_y']);axis=(sin(angle),0,cos(angle))
        for i,(u,v) in enumerate(record['holes']):
            origin=point((u+wall_mm+clearance_mm,v+wall_mm+clearance_mm,0),record)
            # External hardware insertion floor: M2.5 for Pi and M2 for camera.
            # An undersized candidate bore cannot redefine the physical screw.
            hardware_radius = 1.25 if name == 'pi' else 1.0
            required_radius = max(record['bore_diameter']/2, hardware_radius)
            mounts.append(Mount(f'{name}_{i}',origin,axis,required_radius,oz,record['boss_outer_diameter']/2*.999,wall_mm+2.5))
        walls.append(envelope(name+'_floor',(wall_mm/4,wall_mm/4,0),(wall_mm/2,wall_mm/2,wall_mm),record))
        if name=='pi':
            for label,x,width,height in [('hdmi',12.4,13,6),('usb_data',41.4,9,5),('usb_power',54,9,5)]:
                ports.append(envelope(label,(wall_mm+clearance_mm+x-width/2,-6,wall_mm+2.5),(width,wall_mm+8,height),record,'Nominal connector center; plug size and insertion corridor assumed'))
            ports.append(envelope('csi',(ox-wall_mm-1,(oy-12.5)/2,wall_mm+2.5),(wall_mm+3,12.5,3),record))
            ports.append(envelope('sd',(-2,(oy-14)/2,wall_mm+1.5),(wall_mm+3,14,3),record))
        else:
            ports.append(envelope('camera_ribbon',((ox-16)/2,-3,wall_mm+2.5),(16,wall_mm+5,3),record))
    return EngineeringContract(components=tuple(components),ports=tuple(ports),mounts=tuple(mounts),
        wall_witnesses=tuple(walls),density_g_cm3=density_g_cm3,material_source=material_source)
