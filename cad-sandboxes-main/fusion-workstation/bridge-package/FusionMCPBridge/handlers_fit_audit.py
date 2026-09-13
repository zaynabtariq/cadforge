"""Feature-preserving cone creation and exhaustive body/fastener fit inspection."""
import math
import adsk.core
import adsk.fusion
import bridge_helpers as bh
from handlers_mechanical_review import transform

def frustum(d):
    comp,_=bh.get_component_by_name(d['component']);axis=d['axis'];p=d['start'];k={'x':0,'y':1,'z':2}[axis]
    profiles=[]
    for i,r in enumerate([d['radius0'],d['radius1']]):
        offset=(p[k]+i*d['length'])/10
        base={'x':comp.yZConstructionPlane,'y':comp.xZConstructionPlane,'z':comp.xYConstructionPlane}[axis]
        pi=comp.constructionPlanes.createInput();pi.setByOffset(base,adsk.core.ValueInput.createByReal(offset));plane=comp.constructionPlanes.add(pi)
        s=comp.sketches.add(plane);s.name=d['name']+f'_Profile{i}'
        xy={'x':[-p[2],p[1]],'y':[p[0],-p[2]],'z':[p[0],p[1]]}[axis]
        s.sketchCurves.sketchCircles.addByCenterRadius(adsk.core.Point3D.create(xy[0]/10,xy[1]/10,0),r/10)
        profiles.append(s.profiles.item(0));s.isVisible=False;plane.isLightBulbOn=False
    op={'cut':adsk.fusion.FeatureOperations.CutFeatureOperation,'new_body':adsk.fusion.FeatureOperations.NewBodyFeatureOperation}[d.get('operation','new_body')]
    li=comp.features.loftFeatures.createInput(op)
    for p in profiles:li.loftSections.add(p)
    if d.get('operation')=='cut':li.participantBodies=[comp.bRepBodies.itemByName(d['body'])]
    f=comp.features.loftFeatures.add(li);f.name=d['name']
    if d.get('operation')!='cut':f.bodies.item(0).name=d.get('body',d['name'])
    return {'success':True,'name':f.name}

def solids(d):
    mgr=adsk.fusion.TemporaryBRepManager.get();result=[]
    for occ in bh.get_root().occurrences:
        name=occ.component.name
        if d.get('include') is not None and name not in d['include']:continue
        if name in d.get('exclude_components',[]):continue
        for b in occ.component.bRepBodies:
            if b.name in d.get('exclude_bodies',[]):continue
            cp=mgr.copy(b)
            if name in d.get('transforms',{}):mgr.transform(cp,transform(d['transforms'][name]))
            result.append((name,b.name,cp))
    return result

def overlapping(a,b):
    aa,bb=a.boundingBox,b.boundingBox
    return all(getattr(aa.maxPoint,k)>getattr(bb.minPoint,k)+1e-7 and getattr(bb.maxPoint,k)>getattr(aa.minPoint,k)+1e-7 for k in ['x','y','z'])

def audit(d):
    mgr=adsk.fusion.TemporaryBRepManager.get();ss=solids(d);hits=[];errors=[];tested=0;selected=0;focus=set(d.get('focus_bodies',[]))
    # Cache COM bounding-box properties once per body, not once per pair.
    bounds={}
    for _,_,solid in ss:
        bb=solid.boundingBox;lo=bb.minPoint;hi=bb.maxPoint
        bounds[id(solid)]=([lo.x,lo.y,lo.z],[hi.x,hi.y,hi.z])
    for i,(ca,na,a) in enumerate(ss):
        for cb,nb,b in ss[i+1:]:
            if focus and na not in focus and nb not in focus:continue
            selected+=1
            alo,ahi=bounds[id(a)];blo,bhi=bounds[id(b)]
            if not all(ahi[k]>blo[k]+1e-7 and bhi[k]>alo[k]+1e-7 for k in range(3)):continue
            tested+=1;c=mgr.copy(a)
            try:
                if not mgr.booleanOperation(c,b,adsk.fusion.BooleanTypes.IntersectionBooleanType):raise RuntimeError('Boolean operation failed')
                vol=c.volume*1000
                if vol>1e-5:hits.append({'a':na,'b':nb,'a_component':ca,'b_component':cb,'volume_mm3':round(vol,6)})
            except Exception as e:errors.append({'a':na,'b':nb,'error':str(e)})
    ds=[];lookup={n:b for _,n,b in ss}
    for a,b in d.get('measure_pairs',[]):
        try:
            r=bh.app.measureManager.measureMinimumDistance(lookup[a],lookup[b]);ds.append({'a':a,'b':b,'distance_mm':r.value*10})
        except Exception as e:errors.append({'a':a,'b':b,'measure_error':str(e)})
    return {'bodies':len(ss),'all_pairs':len(ss)*(len(ss)-1)//2,'selected_pairs':selected,'boolean_tests':tested,'interferences':hits,'errors':errors,'clearances':ds}

def inventory(d):
    items=[]
    for occ in bh.get_root().occurrences:
        c=occ.component
        for b in c.bRepBodies:
            bb=b.boundingBox;holes=[]
            for f in b.faces:
                cy=adsk.core.Cylinder.cast(f.geometry)
                if cy:
                    holes.append({'radius_mm':cy.radius*10,'origin_mm':[cy.origin.x*10,cy.origin.y*10,cy.origin.z*10],'axis':[cy.axis.x,cy.axis.y,cy.axis.z],'reversed':f.isParamReversed,'area_mm2':f.area*100})
            items.append({'component':c.name,'body':b.name,'volume_mm3':b.volume*1000,'is_solid':b.isSolid,'bounds_mm':[[bb.minPoint.x*10,bb.minPoint.y*10,bb.minPoint.z*10],[bb.maxPoint.x*10,bb.maxPoint.y*10,bb.maxPoint.z*10]],'cylindrical_faces':holes})
    return {'items':items}

def probes(d):
    mgr=adsk.fusion.TemporaryBRepManager.get();ss=solids(d);results=[]
    for p in d['probes']:
        a=adsk.core.Point3D.create(*[v/10 for v in p['start']]);b=adsk.core.Point3D.create(*[v/10 for v in p['end']]);c=mgr.createCylinderOrCone(a,p['radius']/10,b,p['radius']/10)
        hits=[]
        for comp,name,body in ss:
            if name in p.get('ignore_bodies',[]) or comp in p.get('remove_components',[]):continue
            if not overlapping(c,body):continue
            cp=mgr.copy(c)
            if not mgr.booleanOperation(cp,body,adsk.fusion.BooleanTypes.IntersectionBooleanType):raise RuntimeError(f'Probe boolean failed: {name}')
            if cp.volume*1000>1e-5:hits.append({'body':name,'component':comp,'volume_mm3':cp.volume*1000})
        results.append({'id':p['id'],'collisions':hits})
    return {'results':results}


def rotate_sketch(d):
    s=bh.get_sketch(d['sketch']);entities=adsk.core.ObjectCollection.create()
    for c in s.sketchCurves:entities.add(c)
    m=adsk.core.Matrix3D.create();p=d['center']
    m.setToRotation(math.radians(d['degrees']),adsk.core.Vector3D.create(0,0,1),adsk.core.Point3D.create(p[0]/10,p[1]/10,0))
    return {'success':s.move(entities,m)}

FIT_AUDIT_ROUTES={'/fit_rotate_sketch':rotate_sketch,'/mechanical_frustum':frustum,'/fit_audit':audit,'/fit_inventory':inventory,'/fit_probes':probes}
