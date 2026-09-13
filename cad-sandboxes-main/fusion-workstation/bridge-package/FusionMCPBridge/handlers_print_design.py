"""Structured parametric feature batches, millimetres; no executable input."""
import math
import adsk.core,adsk.fusion
import bridge_helpers as bh

def point(p):return adsk.core.Point3D.create(p[0]/10,p[1]/10,0)
def sketch(c,n,axis,off,shape):
 base={'x':c.yZConstructionPlane,'y':c.xZConstructionPlane,'z':c.xYConstructionPlane}[axis]
 if off:
  pi=c.constructionPlanes.createInput();pi.setByOffset(base,adsk.core.ValueInput.createByReal(off/10));base=c.constructionPlanes.add(pi);base.isLightBulbOn=False
 s=c.sketches.add(base);s.name=n
 if 'circle' in shape:
  p,r=shape['circle'];s.sketchCurves.sketchCircles.addByCenterRadius(point(p),r/10)
 elif 'capsule' in shape:
  a,b,r=shape['capsule'];dx=b[0]-a[0];dy=b[1]-a[1];l=math.hypot(dx,dy);u=[dx/l,dy/l];v=[-u[1],u[0]]
  plus=lambda p,k:[p[i]+v[i]*r*k for i in range(2)]
  ap,am,bp,bm=plus(a,1),plus(a,-1),plus(b,1),plus(b,-1)
  s.sketchCurves.sketchLines.addByTwoPoints(point(ap),point(bp));s.sketchCurves.sketchLines.addByTwoPoints(point(bm),point(am))
  s.sketchCurves.sketchArcs.addByThreePoints(point(bp),point([b[i]+u[i]*r for i in range(2)]),point(bm))
  s.sketchCurves.sketchArcs.addByThreePoints(point(am),point([a[i]-u[i]*r for i in range(2)]),point(ap))
 else:
  pts=shape['polygon']
  for a,b in zip(pts,pts[1:]+pts[:1]):s.sketchCurves.sketchLines.addByTwoPoints(point(a),point(b))
 if s.profiles.count!=1:raise ValueError(n+': expected one profile')
 s.isVisible=False;return s

def batch(d):
 root=bh.get_root();name=d['component'];c=None
 for o in root.occurrences:
  if o.component.name==name:c=o.component;break
 if not c:c=root.occurrences.addNewComponent(adsk.core.Matrix3D.create()).component;c.name=name
 done=[]
 ops={'new_body':adsk.fusion.FeatureOperations.NewBodyFeatureOperation,'cut':adsk.fusion.FeatureOperations.CutFeatureOperation,'join':adsk.fusion.FeatureOperations.JoinFeatureOperation}
 for k,a in enumerate(d['features']):
  n=a['name'];body=a.get('body',name);op=a.get('operation','new_body');ss=[]
  if 'loft' in a:
   for i,p in enumerate(a['loft']):ss.append(sketch(c,n+f'_Profile{i}',a['axis'],p['offset'],p))
   inp=c.features.loftFeatures.createInput(ops[op])
   for s in ss:inp.loftSections.add(s.profiles.item(0))
   if op!='new_body':inp.participantBodies=[c.bRepBodies.itemByName(body)]
   f=c.features.loftFeatures.add(inp)
  else:
   s=sketch(c,n+'_Profile',a['axis'],a['offset'],a);inp=c.features.extrudeFeatures.createInput(s.profiles.item(0),ops[op])
   if op!='new_body':inp.participantBodies=[c.bRepBodies.itemByName(body)]
   inp.setOneSideExtent(adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByReal(a['length']/10)),adsk.fusion.ExtentDirections.PositiveExtentDirection)
   f=c.features.extrudeFeatures.add(inp)
  f.name=n
  if op=='new_body':f.bodies.item(0).name=body
  if f.healthState!=adsk.fusion.FeatureHealthStates.HealthyFeatureHealthState:raise ValueError(n+': '+f.errorOrWarningMessage)
  done.append(n)
 adsk.doEvents();return {'success':True,'component':name,'features':len(done),'bodies':c.bRepBodies.count}
def move_bodies(d):
 c,_=bh.get_component_by_name(d['component']);coll=adsk.core.ObjectCollection.create()
 for name in d['bodies']:
  b=c.bRepBodies.itemByName(name)
  if not b:raise ValueError('Body not found: '+name)
  coll.add(b)
 inp=c.features.moveFeatures.createInput2(coll);m=adsk.core.Matrix3D.create()
 m.translation=adsk.core.Vector3D.create(*[v/10 for v in d['translation']]);inp.defineAsFreeMove(m)
 f=c.features.moveFeatures.add(inp);f.name=d['name']
 if f.healthState!=adsk.fusion.FeatureHealthStates.HealthyFeatureHealthState:raise ValueError(f.errorOrWarningMessage)
 return {'success':True,'feature':f.name}

PRINT_DESIGN_ROUTES={'/print_feature_batch':batch,'/print_move_bodies':move_bodies}


def remove_body(d):
 c,_=bh.get_component_by_name(d['component'])
 if not c:raise ValueError('Component not found')
 b=c.bRepBodies.itemByName(d['body_name'])
 if not b:raise ValueError('Body not found')
 f=c.features.removeFeatures.add(b);f.name='Remove_'+d['body_name']
 if not f or f.healthState!=adsk.fusion.FeatureHealthStates.HealthyFeatureHealthState:raise ValueError('Remove failed')
 return {'success':True,'removed':d['body_name']}
PRINT_DESIGN_ROUTES['/print_remove_body']=remove_body
