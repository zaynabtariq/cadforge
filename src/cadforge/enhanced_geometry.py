"""Development assembly with camera pocket and geometrically mated fasteners.

All sizes in mm. Pi envelope 65x30x6 and camera PCB envelope 25x24x6
are explicit editable assumptions, not manufacturer-certified footprints. Screws
are unthreaded clearance/retention envelopes; thread engagement is not simulated.
The frozen baseline backend remains independent of this development backend.
"""
import cadquery as cq
from .schema import DesignSpec, CheckResult, ValidationReport
from .geometry import BuildResult, box, cylinder, build_design as baseline_build
from .validation import validate_design as baseline_validate


def build_design(spec: DesignSpec) -> BuildResult:
    if spec.family not in ('glasses', 'enclosure'):
        return baseline_build(spec)
    p=spec.resolved()
    if any(v <= 0 for v in p.values()):
        raise ValueError('Dimensions must be positive')
    w,c,d=p['wall'],p['clearance'],p['screw_diameter']
    if d < 1 or d > 6:
        raise ValueError('Supported screw nominal diameter is 1 to 6 mm')
    camera=(p.get('camera_width',25),p.get('camera_height',24),p.get('camera_depth',6))
    parts,probes={},{}
    # Corner bosses sit outside the rectangular component envelope.
    def pocket(prefix, dims, origin, aperture=False):
        bx,by,bz=dims
        margin=d+2*w
        ix,iy=bx+2*c+2*margin,by+2*c+2*margin
        ox,oy,oz=ix+2*w,iy+2*w,bz+c+w
        shell=box(ox,oy,oz).cut(box(ix,iy,oz,(w,w,w)))
        lid=box(ox,oy,p['lid_thickness'],(0,0,oz))
        axes=[(w+margin/2,w+margin/2),(ox-w-margin/2,oy-w-margin/2)]
        if prefix=='pi':
            axes += [(ox-w-margin/2,w+margin/2),(w+margin/2,oy-w-margin/2)]
        for i,(x,y) in enumerate(axes):
            boss=cylinder(d/2+w,oz-w,(x,y,w))
            bore=cylinder(d/2,oz+p['lid_thickness']+2,(x,y,-1))
            shell=shell.fuse(boss).cut(bore)
            lid=lid.cut(bore)
            probes[f'{prefix}_screw_hole_{i}']=cylinder(d*.48,oz+p['lid_thickness']+2,(x,y,-1)).translate(origin)
            # Shaft reaches through boss; head contacts top face of removable lid.
            screw=cylinder(d*.44,oz+p['lid_thickness'],(x,y,0)).fuse(cylinder(d*.9,d*.6,(x,y,oz+p['lid_thickness'])))
            parts[f'{prefix}_screw_{i}']=screw.translate(origin)
        if aperture:
            r=p['camera_diameter']/2
            if 2*r >= min(bx,by):
                raise ValueError('Camera lens opening must fit within camera envelope')
            opening=cylinder(r,w+2,(ox/2,oy/2,-1))
            shell=shell.cut(opening)
            probes['camera_lens_opening']=cylinder(r*.98,w+2,(ox/2,oy/2,-1)).translate(origin)
        probes[f'{prefix}_component_clearance']=box(bx,by,bz,(w+margin+c,w+margin+c,w+c/2)).translate(origin)
        probes[f'{prefix}_wall_witness']=box(w/2,w/2,w,(w/4,w/4,0)).translate(origin)
        parts['housing' if prefix=='pi' else 'camera_housing']=shell.translate(origin)
        parts['lid' if prefix=='pi' else 'camera_lid']=lid.translate(origin)
        return ox,oy,oz
    # Compute housing width for placement without executing geometry twice.
    margin=d+2*w
    ox=p['board_length']+2*c+2*margin+2*w
    oy=p['board_width']+2*c+2*margin+2*w
    origin=(0,0,0)
    pad=max(10, d+4*w)
    if spec.family=='glasses':
        old=baseline_build(spec)
        frame=old.parts['frame']
        fx=frame.BoundingBox().xmax
        dz=p['temple_length']*.35
        origin=(fx+pad+c,p['lens_height']-oy+pad/2,dz)
        # Frame boss and housing tab meet on a plane; bore lies beside temple.
        px,py=fx+pad/2,p['lens_height']+w/2
        frame=frame.fuse(box(pad,pad,w,(fx,py-pad/2,dz-w)))
        mount_bore=cylinder(d/2,2*w+2,(px,py,dz-w-1))
        parts['frame']=frame.cut(mount_bore)
        parts['temple_screw']=cylinder(d*.44,2*w,(px,py,dz-w)).fuse(cylinder(d*.9,d*.6,(px,py,dz+w)))
        probes['temple_fastener_hole']=cylinder(d*.48,2*w,(px,py,dz-w))
    ox,oy,oz=pocket('pi',(p['board_length'],p['board_width'],p['board_height']),origin)
    camera_origin=(origin[0],origin[1]-camera[1]-2*c-2*margin-4*w,origin[2])
    cx,cy,cz=pocket('camera',camera,camera_origin,True)
    # A solid connecting web joins the two pockets along their outside walls.
    connector=box(min(ox,cx),2*w,w,(origin[0],origin[1]-2*w,origin[2]))
    parts['housing']=parts['housing'].fuse(connector).fuse(parts.pop('camera_housing'))
    if spec.family=='glasses':
        tab=box(pad+c+w,pad,w,(fx,py-pad/2,dz)).cut(mount_bore)
        parts['housing']=parts['housing'].fuse(tab)
    assembly=cq.Assembly(name=spec.name)
    for name,shape in parts.items():
        assembly.add(shape,name=name)
    return BuildResult(spec,parts,assembly,measurements={'camera_width_mm':camera[0],'camera_height_mm':camera[1],'camera_depth_mm':camera[2]},probes=probes)


def validate_enhanced_design(result: BuildResult) -> ValidationReport:
    if result.spec.family not in ('glasses','enclosure'):
        return baseline_validate(result)
    checks=[];measurements=dict(result.measurements)
    def check(name,passed,actual=None,expected=None):
        checks.append(CheckResult(name=name,passed=bool(passed),actual=actual,expected=expected))
    plastic={name:shape for name,shape in result.parts.items() if 'screw' not in name}
    for name,shape in result.parts.items():
        check('valid_solid_'+name,shape.isValid() and len(shape.Solids())==1,len(shape.Solids()),1)
        check('positive_volume_'+name,shape.Volume()>1e-6,shape.Volume(),'>0')
    names=list(result.parts)
    for i,name in enumerate(names):
        for other in names[i+1:]:
            overlap=result.parts[name].intersect(result.parts[other]).Volume()
            check('noncollision_'+name+'_'+other,overlap<1e-5,overlap,'<1e-5 mm3')
    for name,probe in result.probes.items():
        overlap=sum(shape.intersect(probe).Volume() for shape in plastic.values())
        if 'wall_witness' in name:
            check(name,abs(overlap-probe.Volume())<1e-5,overlap,probe.Volume())
            check('minimum_wall_'+name,probe.BoundingBox().zlen>=1.2-1e-6,probe.BoundingBox().zlen,'>=1.2 mm')
        else:
            check(name,overlap<1e-5,overlap,'<1e-5 mm3')
            if 'component_clearance' in name:
                distance=min(shape.distance(probe) for shape in plastic.values())
                measurements[name+'_mm']=distance
                check('minimum_'+name,distance>=.2-1e-6,distance,'>=0.2 mm')
    # Confirm assembled lids physically contact housing; no floating display offsets.
    for name in ('lid','camera_lid'):
        distance=result.parts['housing'].distance(result.parts[name])
        check(name+'_seated',distance<1e-6,distance,0)
    if 'frame' in result.parts:
        distance=result.parts['housing'].distance(result.parts['frame'])
        check('temple_joint_contact',distance<1e-6,distance,0)
    check('camera_pocket_present','camera_component_clearance' in result.probes)
    check('screw_holes_present',sum('screw_hole' in key for key in result.probes)>=6)
    return ValidationReport(passed=all(c.passed for c in checks),checks=checks,measurements=measurements,limitations=[
        'Prototype geometry only: no FEA, fatigue, thermal, electrical, optical or ergonomic validation.',
        'Pi 65x30x6 mm and camera 25x24x6 mm envelopes are editable assumptions, not verified vendor footprints.',
        'Fasteners are unthreaded envelopes; thread engagement, tolerances, preload, washers and assembly tools remain unverified.',
        'Camera is enclosed in a dedicated pocket; PCB standoffs, lens optical alignment and cable/connector routing remain unresolved.',
        'Electronics access, ventilation and wearable mass distribution remain unresolved.'
    ])


def export_design(result: BuildResult, output_dir) -> dict[str,str]:
    """Export assembly and source that faithfully regenerates this enhanced backend."""
    from pathlib import Path
    from .geometry import export_design as baseline_export
    paths=baseline_export(result,output_dir)
    source=Path(paths['python'])
    source.write_text(source.read_text().replace('from cadforge.geometry import build_design, export_design','from cadforge.enhanced_geometry import build_design, export_design'))
    return paths
