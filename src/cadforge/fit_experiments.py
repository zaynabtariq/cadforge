"""Discover engineering factors by executing BRep fit/boss experiments.

All dimensions are ideal CAD millimeters. These experiments do not calibrate a
printer or assert a manufactured clearance; physical process offsets are unknown.
"""
from __future__ import annotations
import hashlib
import json
import math
from dataclasses import replace
from pathlib import Path
import uuid
import cadquery as cq
from OCP.BRepAdaptor import BRepAdaptor_Surface
from .continual import Measurement


def make_coupon(p):
    d=p['bore_diameter']; outer=p.get('boss_outer_diameter',16.)
    if not 0<d<outer<50:
        raise ValueError('Require 0 < bore < boss diameter < 50 mm')
    family=int(p.get('family_code',0))
    plate=cq.Workplane('XY').box(24,20,3,centered=(True,True,False)).val()
    if family==1:
        plate=plate.fuse(cq.Workplane('XY').box(24,3,12,centered=False).translate((-12,7,0)).val())
    elif family==2:
        for x in (-12,9):
            plate=plate.fuse(cq.Workplane('XY').box(3,20,10,centered=False).translate((x,-10,0)).val())
    boss=cq.Workplane('XY').circle(outer/2).extrude(8).val()
    bore=cq.Workplane('XY').circle(d/2).extrude(10).translate((0,0,-1)).val()
    return plate.fuse(boss).cut(bore)


def measure_coupon(p):
    shape=make_coupon(p)
    radii=[]
    for face in shape.Faces():
        if face.geomType()=='CYLINDER':
            radii.append(BRepAdaptor_Surface(face.wrapped).Cylinder().Radius())
    hole_radius=min(radii);outer_radius=max(radii)
    # Screw insertion path includes the engineering-requested radial clearance.
    probe=cq.Workplane('XY').circle(p['fastener_diameter']/2+p['radial_clearance']).extrude(10).translate((0,0,-1)).val()
    overlap=shape.intersect(probe).Volume()
    measured_wall=outer_radius-hole_radius
    checks={'valid_solid':shape.isValid() and len(shape.Solids())==1,
            'screw_insertion_clearance':overlap<1e-6,
            'boss_radial_wall':measured_wall>=p.get('min_wall',1.)-1e-7}
    return Measurement(all(checks.values()),{'bore_diameter':2*hole_radius,'boss_outer_diameter':2*outer_radius,
        'radial_wall':measured_wall,'screw_overlap_mm3':overlap},tuple(k for k,v in checks.items() if not v),checks)


def boundary_executor(target, directory, *, max_trials=80, increment=.1):
    """Record initial failure and the first successful measured repair boundary."""
    if target not in ('bore_diameter','boss_outer_diameter'):
        raise ValueError('unknown fitted command')
    if not isinstance(max_trials, int) or max_trials < 1:
        raise ValueError('max_trials must be a positive integer')
    if not math.isfinite(increment) or increment <= 0:
        raise ValueError('increment must be finite and positive')
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    def execute(parameters,case_id):
        trials=[]; p=dict(parameters)
        initial=None;successful=None
        execution_exception=None
        try:
            for trial in range(max_trials):
                attempted={'trial_index':trial,'parameters':dict(p)}
                trials.append(attempted)
                measurement=measure_coupon(p)
                measurement.validate()
                if initial is None: initial=measurement
                attempted.update({'passed':measurement.passed,'checks':measurement.checks,
                                  'measurements':measurement.measurements,'failure_codes':measurement.failure_codes})
                if measurement.passed:
                    successful=measurement
                    break
                p[target]=round(p[target]+increment,8)
        except Exception as error:
            execution_exception={'type':type(error).__name__,'message':str(error),
                                 'trial_index':len(trials)-1,'parameters':dict(p)}
            if trials:
                trials[-1].update({'passed':False,'checks':{'execution':False},'measurements':{},
                                   'execution_exception':execution_exception})
        finally:
            digests=_write_audit(directory,case_id,{
                'case_id':case_id,'target':target,'increment':increment,'max_trials':max_trials,
                'trials':trials,'attempted_cad_trials':len(trials),
                'execution_exception':execution_exception,
                'basis':'ideal BRep millimeter geometry; no printer calibration',
            })
        if execution_exception is not None:
            return Measurement(False,{'cad_trials':float(len(trials))},
                               ('execution:'+execution_exception['type'],),{'execution':False},digests)
        if successful is None:
            return Measurement(False,{'cad_trials':float(len(trials))},('search_exhausted',),{'boundary_found':False},digests)
        # passed describes the original trial; measurements contains the executed
        # boundary. The fitter therefore retains a real diagnosed initial failure.
        measured=dict(successful.measurements)
        measured['cad_trials']=float(len(trials))
        return Measurement(initial.passed,measured,initial.failure_codes,initial.checks,digests)
    return execute


def verification_executor(directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    def execute(parameters,case_id):
        execution_exception=None
        measured=None
        try:
            measured=measure_coupon(parameters)
            measured.validate()
        except Exception as error:
            execution_exception={'type':type(error).__name__,'message':str(error)}
            measured=Measurement(False,{},('execution:'+type(error).__name__,),{'execution':False})
        finally:
            digests=_write_audit(directory,case_id,{
                'case_id':case_id,'parameters':parameters,'measurements':measured.measurements if measured else {},
                'checks':measured.checks if measured else {},'passed':measured.passed if measured else False,
                'execution_exception':execution_exception,
            })
        return replace(measured,artifact_digests=measured.artifact_digests|digests)
    return execute


def _write_audit(directory,case_id,payload):
    """Keep every attempt; untrusted case IDs never become path components."""
    safe_id=hashlib.sha256(str(case_id).encode()).hexdigest()
    path=Path(directory)/(safe_id+'-'+uuid.uuid4().hex+'.json')
    encoded=json.dumps(payload,sort_keys=True,indent=2,allow_nan=False)+'\n'
    with path.open('x') as stream:
        stream.write(encoded)
    return {str(path.resolve()):hashlib.sha256(path.read_bytes()).hexdigest()}
