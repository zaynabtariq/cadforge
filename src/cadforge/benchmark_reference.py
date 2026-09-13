"""Frozen numerical contract witnesses; never modify after benchmark freeze."""
from dataclasses import dataclass, field
from pathlib import Path
import json
import cadquery as cq
from .schema import DesignSpec

@dataclass
class BuildResult:
    spec: DesignSpec
    parts: dict[str, cq.Shape]
    assembly: cq.Assembly
    measurements: dict[str, float] = field(default_factory=dict)
    probes: dict[str, cq.Shape] = field(default_factory=dict)

def box(x, y, z, at=(0, 0, 0)):
    return cq.Workplane('XY').box(x, y, z, centered=False).translate(at).val()

def cylinder(r, h, at=(0, 0, 0)):
    return cq.Workplane('XY').circle(r).extrude(h).translate(at).val()

def build_design(spec: DesignSpec) -> BuildResult:
    p = spec.resolved()
    # Fail before OCC sees degenerate or negative primitives.
    for k in p:
        if p[k] <= 0:
            raise ValueError(f'{k} must be positive')
    w, c = p['wall'], p['clearance']
    parts, probes = {}, {}
    if spec.family in ('glasses', 'enclosure'):
        ix, iy, iz = p['board_length'] + 2*c, p['board_width'] + 2*c, p['board_height'] + c
        ox, oy, oz = ix + 2*w, iy + 2*w, iz + w
        # Camera window through floor; removable lid exported as its own named solid.
        base = box(ox, oy, oz).cut(box(ix, iy, iz + 1, (w, w, w)))
        r = p['camera_diameter']/2
        if 2*r + 2*w >= min(ox, oy):
            raise ValueError('camera_diameter does not fit housing')
        aperture = cylinder(r, w+2, (ox/2, oy/2, -1))
        parts['housing'] = base.cut(aperture)
        parts['lid'] = box(ox, oy, p['lid_thickness'], (0, 0, oz+c))
        probes['component_clearance'] = box(p['board_length'], p['board_width'], p['board_height'], (w+c, w+c, w+c/2))
        probes['camera_aperture'] = cylinder(r*0.98, w+2, (ox/2, oy/2, -1))
        probes['floor_wall'] = box(w/2, w/2, w, (w*1.1, w*1.1, 0))
        if spec.family == 'glasses':
            lw, lh, bridge, length = (p[k] for k in ('lens_width', 'lens_height', 'bridge', 'temple_length'))
            # Frame lies in XY, temples extend in +Z. Housing mounts at right temple.
            def rim(x):
                return box(lw+2*w,lh+2*w,w,(x,0,0)).cut(box(lw,lh,w+2,(x+w,w,-1)))
            right = lw+2*w+bridge
            frame = rim(0).fuse(rim(right)).fuse(box(bridge, w, w,(lw+2*w,lh/2,0)))
            frame = frame.fuse(box(w,w,length,(0,lh,0))).fuse(box(w,w,length,(right+lw+w,lh,0)))
            parts['frame'] = frame
            # Move electronics housing alongside outer right temple, touching via a mount tab.
            dx, dy, dz = right+lw+2*w, lh-oy+w, length*0.35
            offset = (dx,dy,dz)
            for key in ('housing','lid'):
                parts[key] = parts[key].translate(offset)
            probes = {key: val.translate(offset) for key,val in probes.items()}
            probes['lens_left_aperture'] = box(lw*.98,lh*.98,w+2,(w+lw*.01,w+lh*.01,-1))
            probes['lens_right_aperture'] = box(lw*.98,lh*.98,w+2,(right+w+lw*.01,w+lh*.01,-1))
    elif spec.family == 'bracket':
        width,height,depth,d = (p[k] for k in ('width','height','depth','hole_diameter'))
        if min(width,height,depth) <= 2*w or d+2*w >= min(width,depth):
            raise ValueError('bracket dimensions leave insufficient material around aperture')
        body = box(width,depth,w).fuse(box(width,w,height))
        probe = cylinder(d/2,w+2,(width/2,depth/2,-1))
        parts['bracket'] = body.cut(probe)
        probes['mount_aperture'] = cylinder(d*.49,w+2,(width/2,depth/2,-1))
        probes['base_wall'] = box(w/2,w/2,w,(w,w,0))
    else:
        width,height,gap = (p[k] for k in ('width','height','gap'))
        if height <= 2*w:
            raise ValueError('clip height must exceed twice wall')
        body = box(width,gap+2*w,height).cut(box(width+2,gap,height-w+1,(-1,w,w)))
        parts['clip'] = body
        probes['clip_gap'] = box(width+2,gap*.98,height-w,(-1,w+gap*.01,w+.001))
        probes['base_wall'] = box(width*.5,w*.5,w,(width*.25,w*.25,0))
    assembly = cq.Assembly(name=spec.name)
    for name, shape in parts.items():
        assembly.add(shape, name=name)
    return BuildResult(spec, parts, assembly, probes=probes)
