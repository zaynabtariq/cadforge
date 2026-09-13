"""Measured tool-pocket discovery on ideal development BReps, not fabrication."""
from dataclasses import replace
from pathlib import Path
import cadquery as cq
from OCP.BRepAdaptor import BRepAdaptor_Surface
from .continual import Measurement
from .engineering import EngineeringContract,ToolAccess,assess_geometry
from .fit_experiments import _write_audit


def measure_access(p):
    diameter=p['pocket_diameter']
    if not 3<diameter<20:raise ValueError('Pocket diameter outside coupon support')
    family=int(p.get('family_code',0))
    stock=cq.Workplane('XY').box(30,30,10,centered=(True,True,False)).val()
    if family==1:
        stock=stock.fuse(cq.Workplane('XY').box(30,3,18,centered=False).translate((-15,12,0)).val())
    elif family==2:
        stock=cq.Workplane('XY').circle(18).extrude(10).val()
    elif family!=0:raise ValueError('Unknown development coupon family')
    bore=cq.Solid.makeCylinder(1.5,12,cq.Vector(0,0,-1),cq.Vector(0,0,1))
    stock=stock.cut(bore)
    pocket=cq.Solid.makeCylinder(diameter/2,6,cq.Vector(0,0,5),cq.Vector(0,0,1))
    changed=stock.cut(pocket)
    access=ToolAccess('driver',(0,0,5),(0,0,1),p['tool_diameter']/2+p['radial_clearance'],20,'Explicit ideal development tool envelope')
    report=assess_geometry({'coupon':changed},EngineeringContract(tool_access=(access,)))
    gate=next(g for g in report.gates if g.name=='assembly.tool_access.driver')
    lower=cq.Workplane('XY').box(50,50,5,centered=(True,True,False)).val()
    removed_lower=stock.intersect(lower).cut(changed).Volume()
    radii=[BRepAdaptor_Surface(f.wrapped).Cylinder().Radius() for f in changed.Faces()
           if f.geomType()=='CYLINDER' and 5.01<f.Center().z<9.99]
    checks={'valid_solid':changed.isValid() and len(changed.Solids())==1,
            'tool_corridor':gate.status=='pass','lower_stock_unchanged':removed_lower<1e-7,
            'recognized_pocket':len(radii)==1}
    return Measurement(all(checks.values()),{'pocket_diameter':2*radii[0] if len(radii)==1 else 0.,
        'tool_overlap_mm3':gate.measured,'removed_lower_mm3':removed_lower},
        tuple(k for k,v in checks.items() if not v),checks)


def access_executor(directory,*,discover=False):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    def execute(parameters,case_id):
        p=dict(parameters);trials=[];initial=None;result=None;execution_exception=None
        try:
            for index in range(20 if discover else 1):
                attempted={'trial_index':index,'parameters':dict(p)}
                trials.append(attempted)
                result=measure_access(p)
                result.validate()
                if initial is None:initial=result
                attempted.update({'passed':result.passed,'checks':result.checks,
                                  'measurements':result.measurements,'failure_codes':result.failure_codes})
                if result.passed:break
                p['pocket_diameter']=round(p['pocket_diameter']+.1,8)
        except Exception as error:
            execution_exception={'type':type(error).__name__,'message':str(error),
                                 'trial_index':len(trials)-1,'parameters':dict(p)}
            if trials:
                trials[-1].update({'passed':False,'checks':{'execution':False},'measurements':{},
                                  'execution_exception':execution_exception})
        finally:
            digest=_write_audit(directory,case_id,{'case_id':case_id,'trials':trials,
                'attempted_cad_trials':len(trials),'execution_exception':execution_exception,
                'scope':'ideal tool-access coupons'})
        if execution_exception is not None:
            return Measurement(False,{'cad_trials':len(trials)},
                ('execution:'+execution_exception['type'],),{'execution':False},digest)
        if discover and not result.passed:
            return Measurement(False,{'cad_trials':len(trials)},('search_exhausted',),{'boundary_found':False},digest)
        observed=initial if discover else result
        return replace(observed,measurements=result.measurements|{'cad_trials':len(trials)},artifact_digests=digest)
    return execute
