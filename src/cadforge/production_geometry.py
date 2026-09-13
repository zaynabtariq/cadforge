"""Source-grounded V2 wearable geometry, NOT production certification.

Only nominal board outline/hole patterns are sourced; component heights, plug
keepouts, fastening stack and cable bends require physical verification.
"""
from pathlib import Path
import cadquery as cq
from .schema import DesignSpec
from .geometry import BuildResult, box, cylinder, build_design as base_build, export_design as base_export

PI_SOURCE='https://datasheets.raspberrypi.com/rpizero2/raspberry-pi-zero-2-w-mechanical-drawing.pdf'
CAMERA_SOURCE='https://datasheets.raspberrypi.com/camera/camera-module-3-standard-mechanical-drawing.pdf'


def layout(spec: DesignSpec) -> dict:
    p=spec.resolved();w=p['wall'];c=p['clearance']
    bore=p.get('bore_diameter',2.75)
    boss=p.get('boss_outer_diameter',bore+2*w)
    if w<=0 or c<=0 or bore<=0 or boss<=bore:
        raise ValueError('Positive wall, clearance, bore and boss annulus required')
    fw=2*(p['lens_width']+2*w)+p['bridge']
    pi_depth=w+2.5+p.get('pi_component_height',6)+c+p['lid_thickness']
    camera_width=25+2*(w+c)
    from .operations import translation_for_anchor
    pi_origin=translation_for_anchor((0,30+2*(w+c),0),(fw,p['lens_height']+w,p['temple_length']*.6))
    from .camera_interconnect import reference_interconnect
    return {'units':'mm','engineering_ready':False,'frame_width':fw,'camera_interconnect':reference_interconnect(),
      'pi':{'source':PI_SOURCE,'board_size':[65,30], 'component_min':[w+c,w+c,w+2.5],
        'component_size':[65,30,p.get('pi_component_height',6)],
        'holes':[[3.5,3.5],[61.5,3.5],[3.5,26.5],[61.5,26.5]],
        'bore_diameter':bore,'boss_outer_diameter':boss,'pcb_thickness':1.6,
        'origin':list(pi_origin),'rotation_y':90,'outer_size':[65+2*(w+c),30+2*(w+c),pi_depth],
        'assumptions':['component height','PCB thickness','plug envelopes','M2.5 fastener stack']},
      'camera':{'source':CAMERA_SOURCE,'board_size':[25,23.862],
        'component_min':[w+c,w+c,w+2.5], 'component_size':[25,23.862,11.3],
        'holes':[[2,2],[23,2],[2,14.5],[23,14.5]],
        'bore_diameter':p.get('camera_bore_diameter',2.2),'boss_outer_diameter':4.75,'pcb_thickness':1.12,
        'lens_center':[12.5,14.4],'lens_opening_diameter':p.get('lens_opening_diameter',12),
        'origin':[fw-(p['lens_width']+2*w)/2+camera_width/2,p['lens_height']+2*w,0],
        'rotation_y':180,'outer_size':[camera_width,23.862+2*(w+c),w+2.5+11.3+c+p['lid_thickness']],
        'assumptions':['rectangular total-depth envelope','lens field-of-view opening','fastener stack']},
      'limitations':['No validated FEA/thermal/skin-contact/ergonomic/optical evidence.',
        'Cable channels are routing-space witnesses; minimum bend radius and actual cable compatibility remain blocked.',
        'Connector plug depths/widths and populated-board heights must be measured against purchased hardware.',
        'Lid screws use through-bolt retention concept; nuts, driver access and compression of PCB require prototype review.',
        'Integrated rigid frame/pods require print orientation/support review; not foldable spectacles.']}


def transform(shape, record):
    return shape.rotate((0,0,0),(0,1,0),record['rotation_y']).translate(tuple(record['origin']))


def build_design(spec: DesignSpec) -> BuildResult:
    if spec.family!='glasses':
        return base_build(spec)
    p=spec.resolved();w=p['wall'];c=p['clearance'];data=layout(spec)
    parts={};probes={};measurements={}
    for name in ('pi','camera'):
        rec=data[name];ox,oy,oz=rec['outer_size'];lid_t=p['lid_thickness'];top=oz-lid_t
        shell=box(ox,oy,top).cut(box(ox-2*w,oy-2*w,top,(w,w,w)))
        lid=box(ox,oy,lid_t,(0,0,top))
        for i,(u,v) in enumerate(rec['holes']):
            x,y=u+w+c,v+w+c;r=rec['bore_diameter']/2
            # Posts terminate exactly at PCB support plane, preserving electronics space.
            post=cylinder(rec['boss_outer_diameter']/2,2.5,(x,y,w))
            shell=shell.fuse(post)
            hole=cylinder(r,oz+2,(x,y,-1))
            shell=shell.cut(hole);lid=lid.cut(hole)
            probes[f'{name}_mount_hole_{i}']=transform(cylinder(r*.98,oz+2,(x,y,-1)),rec)
        probes[name+'_component']=transform(box(*rec['component_size'],tuple(rec['component_min'])),rec)
        probes[name+'_floor_wall']=transform(box(w/2,w/2,w,(w/4,w/4,0)),rec)
        if name=='pi':
            # Centers from official drawing; plug size/depth deliberately marked assumed.
            for label,x,width,height in [('hdmi',12.4,13,6),('usb_data',41.4,9,5),('usb_power',54,9,5)]:
                keepout=box(width,w+8,height,(w+c+x-width/2,-6,w+2.5))
                shell=shell.cut(keepout)
                probes['port_'+label]=transform(keepout,rec)
            # CSI opening at high-u end; SD at low-u end. Cable dimensions provisional.
            csi=box(w+3,12.5,3,(ox-w-1,(oy-12.5)/2,w+2.5))
            sd=box(w+3,14,3,(-2,(oy-14)/2,w+1.5))
            shell=shell.cut(csi).cut(sd)
            probes['port_csi']=transform(csi,rec);probes['port_sd']=transform(sd,rec)
            # Vent apertures open on outer lid; thermal adequacy remains unverified.
            for index in range(5):
                vent=box(2,10,lid_t+2,(15+6*index,oy/2-5,top-1))
                lid=lid.cut(vent);probes[f'vent_{index}']=transform(vent,rec)
        else:
            lx,ly=rec['lens_center'];radius=rec['lens_opening_diameter']/2
            opening=cylinder(radius,lid_t+2,(lx+w+c,ly+w+c,top-1))
            lid=lid.cut(opening);probes['lens_aperture']=transform(opening,rec)
            ribbon=box(16,w+5,3,((ox-16)/2,-3,w+2.5))
            shell=shell.cut(ribbon);probes['camera_ribbon_port']=transform(ribbon,rec)
        parts[name+'_pod']=transform(shell,rec);parts[name+'_lid']=transform(lid,rec)
        measurements[name+'_bore_diameter_mm']=rec['bore_diameter']
    # Rigid chassis: frame and pods meet as printable integral material, removing
    # the prior unfastened side-by-side assembly. Removable lids remain distinct.
    frame=base_build(spec).parts['frame']
    pi=parts.pop('pi_pod');camera=parts.pop('camera_pod')
    # Camera sits directly above upper right rim; broad rear web links its base.
    cam=data['camera'];bb=camera.BoundingBox()
    web=box(bb.xlen,w,w,(bb.xmin,p['lens_height']+w,-w))
    chassis=frame.fuse(pi).fuse(camera).fuse(web)
    parts['chassis']=chassis
    # Open cable trough beside the right temple. It represents measurable free
    # routing volume, not an assertion that an FPC can negotiate sharp bends.
    # Resolve route endpoints from transformed connector envelopes. No global
    # Y/Z constants from the previous frame may survive a resized mating layout.
    pi_port=probes['port_csi'].BoundingBox()
    camera_port=probes['camera_ribbon_port'].BoundingBox()
    route_x=pi_port.xmin-2.5
    route_y=pi_port.ymin-1
    cam_center=(camera_port.xmin+camera_port.xmax)/2
    segments=[
        box(4,pi_port.ylen+2,pi_port.zmax,(route_x,route_y,0)),
        box(4,camera_port.ymax-route_y,2-camera_port.zmin,(route_x,route_y,camera_port.zmin)),
        box(route_x+4-cam_center,camera_port.ylen,camera_port.zlen,(cam_center,camera_port.ymin,camera_port.zmin))]
    channel=segments[0]
    for segment in segments[1:]:channel=channel.fuse(segment)
    outer=[]
    for segment in segments:
        bounds=segment.BoundingBox()
        outer.append(box(bounds.xlen+2,bounds.ylen+2,bounds.zlen+2,(bounds.xmin-1,bounds.ymin-1,bounds.zmin-1)))
    trough=outer[0]
    for segment in outer[1:]:trough=trough.fuse(segment)
    trough=trough.cut(channel).cut(probes['port_csi'])
    for body in parts.values():trough=trough.cut(body)
    parts['chassis']=parts['chassis'].cut(channel)
    for probe_name, probe in probes.items():
        if 'floor_wall' not in probe_name:
            trough=trough.cut(probe)
    # Independent gate found a 0.0886 mm3 ring intrusion missed by the 98%
    # diagnostic probe: trim guide with the full nominal hardware bore.
    protected_mounting_voids=[]
    for component_name in ('pi','camera'):
        rec=data[component_name]
        for u,v in rec['holes']:
            bore=transform(cylinder(rec['bore_diameter']/2+1e-4,rec['outer_size'][2]+2,(u+w+c,v+w+c,-1)),rec)
            protected_mounting_voids.append(bore)
    from .operations import preserve_interface_voids
    repaired=preserve_interface_voids(trough,protected_mounting_voids,require_single=False)
    trough=repaired.shape
    measurements['protected_interface_repair_removed_mm3']=repaired.removed_volume_mm3
    # Routing guide currently consists of separate printable segments.
    for index, segment in enumerate(trough.Solids()):
        parts[f'cable_guide_{index}']=segment
    probes['cable_channel']=channel
    assembly=cq.Assembly(name=spec.name)
    for name,shape in parts.items():assembly.add(shape,name=name)
    return BuildResult(spec,parts,assembly,measurements,probes)


def export_design(result, output_dir):
    paths=base_export(result,output_dir)
    source=Path(paths['python']);source.write_text(source.read_text().replace('from cadforge.geometry import build_design, export_design','from cadforge.production_geometry import build_design, export_design'))
    import json
    layout_path=Path(output_dir)/'hardware_layout.json';layout_path.write_text(json.dumps(layout(result.spec),indent=2)+'\n')
    paths['hardware_layout']=str(layout_path.resolve())
    from .handoff import write_handoff
    paths['manufacturing_manifest']=write_handoff(result,paths,output_dir)
    from .handoff_geometry import screen_handoff_geometry
    screen=screen_handoff_geometry(paths['manufacturing_manifest'])
    screen_path=Path(output_dir)/'geometry-screen.json'
    screen_path.write_text(json.dumps(screen,indent=2,allow_nan=False)+'\n')
    paths['geometry_screen']=str(screen_path.resolve())
    return paths
