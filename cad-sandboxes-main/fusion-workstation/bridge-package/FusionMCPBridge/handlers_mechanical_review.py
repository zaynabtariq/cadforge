"""Generic review helpers: posed solid checks, centered as-built joints, display.
Uses temporary BReps for collision checks; never mutates production geometry.
All distances in the request are mm, rotations in degrees about world Y.
"""
import math
import adsk.core
import adsk.fusion
from bridge_helpers import get_design, get_root, get_component_by_name, get_sketch
import bridge_helpers as _bh

def transform(spec):
    m=adsk.core.Matrix3D.create()
    angle=math.radians(spec.get('angle',0))
    p=spec.get('origin',[0,0,0])
    m.setToRotation(angle,adsk.core.Vector3D.create(0,1,0),adsk.core.Point3D.create(*[v/10 for v in p]))
    d=spec.get('translate',[0,0,0]);v=m.translation
    m.translation=adsk.core.Vector3D.create(v.x+d[0]/10,v.y+d[1]/10,v.z+d[2]/10)
    return m

def handle_check_pose(body):
    root=get_root();mgr=adsk.fusion.TemporaryBRepManager.get();solids=[]
    include=body.get('include');transforms=body.get('transforms',{})
    for occ in root.occurrences:
        name=occ.component.name
        if include is not None and name not in include:continue
        for b in occ.component.bRepBodies:
            cp=mgr.copy(b)
            if name in transforms:mgr.transform(cp,transform(transforms[name]))
            solids.append((name,b.name,cp))
    overlaps=[];tests=0;failures=[]
    for i,(ca,na,a) in enumerate(solids):
        for cb,nb,b in solids[i+1:]:
            if ca==cb:continue
            aa,bb=a.boundingBox,b.boundingBox
            if any(getattr(aa.maxPoint,k)<=getattr(bb.minPoint,k)+1e-7 or getattr(bb.maxPoint,k)<=getattr(aa.minPoint,k)+1e-7 for k in ['x','y','z']):continue
            tests+=1;test=mgr.copy(a)
            try:
                ok=mgr.booleanOperation(test,b,adsk.fusion.BooleanTypes.IntersectionBooleanType)
                if not ok:failures.append([na,nb]);continue
                v=test.volume*1000
                if v>1e-5:overlaps.append({'a':na,'b':nb,'volume_mm3':round(v,6)})
            except Exception as e:failures.append({'a':na,'b':nb,'error':str(e)})
    return {'solid_count':len(solids),'boolean_tests':tests,'overlaps':overlaps,'failures':failures}

def handle_joint_at(body):
    root=get_root();_,a=get_component_by_name(body['component1']);_,b=get_component_by_name(body['component2'])
    if root.asBuiltJoints.itemByName(body['name']):return {'success':True,'exists':True}
    p=body['point'];want=adsk.core.Point3D.create(*[x/10 for x in p]);edges=[]
    for solid in a.component.bRepBodies:
        for edge in solid.edges:
            g=adsk.core.Circle3D.cast(edge.geometry) or adsk.core.Arc3D.cast(edge.geometry)
            if g and abs(abs(g.normal.y)-1)<1e-5:edges.append((g.center.distanceTo(want),edge))
    if not edges:raise ValueError('No circular edge parallel to Y on first component')
    distance,edge=min(edges,key=lambda x:x[0])
    if distance>0.01:raise ValueError('No circular edge centered at requested point')
    geo=adsk.fusion.JointGeometry.createByCurve(edge.createForAssemblyContext(a),adsk.fusion.JointKeyPointTypes.CenterKeyPoint)
    ji=root.asBuiltJoints.createInput(a,b,geo)
    ji.setAsRevoluteJointMotion(adsk.fusion.JointDirections.ZAxisJointDirection)
    j=root.asBuiltJoints.add(ji);j.name=body['name']
    return {'success':True,'name':j.name,'axis':[j.jointMotion.rotationAxisVector.x,j.jointMotion.rotationAxisVector.y,j.jointMotion.rotationAxisVector.z]}

def handle_review_display(body):
    root=get_root();design=get_design()
    _bh.app.userInterface.activeSelections.clear()
    if body.get('document_name'):
        _bh.app.activeDocument.name=body['document_name']
    for occ in root.occurrences:
        c=occ.component
        c.opacity=1.0
        for s in c.sketches:s.isVisible=False
        for p in c.constructionPlanes:p.isLightBulbOn=False
        c.isOriginFolderLightBulbOn=False
        if c.name in body.get('hide',[]):occ.isLightBulbOn=False
        if c.name in body.get('show',[]):occ.isLightBulbOn=True
        color=body.get('colors',{}).get(c.name)
        if color:
            apps=design.appearances
            appearance=apps.itemByName('ReviewPlastic_'+c.name)
            if not appearance:
                base=None
                for lib in _bh.app.materialLibraries:
                    for candidate in lib.appearances:
                        if candidate.name=='Plastic - Matte (White)':
                            base=candidate;break
                    if base:break
                if base is None:raise ValueError('Matte plastic appearance missing')
                appearance=apps.addByCopy(base,'ReviewPlastic_'+c.name)
            prop=appearance.appearanceProperties.itemById('opaque_albedo')
            if prop is None:prop=appearance.appearanceProperties.itemById('generic_diffuse')
            if prop:prop.value=adsk.core.Color.create(*color,255)
            for b in c.bRepBodies:b.appearance=appearance
    root.isOriginFolderLightBulbOn=False
    root.isJointsFolderLightBulbOn=False
    return {'success':True}

def handle_joint_drive(body):
    j=get_root().asBuiltJoints.itemByName(body['name'])
    if 'limits' in body:
        limits=j.jointMotion.rotationLimits
        limits.minimumValue=math.radians(body['limits'][0])
        limits.maximumValue=math.radians(body['limits'][1])
        limits.isMinimumValueEnabled=True
        limits.isMaximumValueEnabled=True
    j.jointMotion.rotationValue=math.radians(body['degrees'])
    adsk.doEvents()
    return {'success':True,'degrees':math.degrees(j.jointMotion.rotationValue)}

def handle_shift_sketch(body):
    sketch=get_sketch(body['sketch'])
    entities=adsk.core.ObjectCollection.create()
    for c in sketch.sketchCurves:entities.add(c)
    m=adsk.core.Matrix3D.create()
    m.translation=adsk.core.Vector3D.create(*[x/10 for x in body['translation']])
    return {'success':sketch.move(entities,m)}

def handle_live_geometry(body):
    root=get_root();result={}
    for name,points in body.get('points',{}).items():
        _,occ=get_component_by_name(name);out=[]
        for p in points:
            v=adsk.core.Point3D.create(*[x/10 for x in p]);v.transformBy(occ.transform2)
            out.append([x*10 for x in [v.x,v.y,v.z]])
        result[name]=out
    return result

def handle_component_fillet(body):
    comp,occ=get_component_by_name(body['component'])
    target=comp.bRepBodies.itemByName(body.get('body',body['component']))
    edges=adsk.core.ObjectCollection.create()
    for p in body['points']:
        candidates=[]
        for e in target.edges:
            bb=e.boundingBox
            mid=[(getattr(bb.minPoint,k)+getattr(bb.maxPoint,k))*5 for k in ['x','y','z']]
            candidates.append((sum((a-b)**2 for a,b in zip(mid,p)),e))
        d,e=min(candidates,key=lambda t:t[0])
        if d>0.01:raise ValueError('Requested edge midpoint not found')
        edges.add(e)
    fi=comp.features.filletFeatures.createInput()
    fi.edgeSetInputs.addConstantRadiusEdgeSet(edges,adsk.core.ValueInput.createByReal(body['radius']/10),False)
    feature=comp.features.filletFeatures.add(fi)
    feature.name=body['name']
    return {'success':True,'name':feature.name}

def handle_rigid(body):
    root=get_root();_,a=get_component_by_name(body['component1']);_,b=get_component_by_name(body['component2'])
    ji=root.asBuiltJoints.createInput(a,b,None);ji.setAsRigidJointMotion()
    j=root.asBuiltJoints.add(ji);j.name=body['name']
    return {'success':True,'name':j.name}

def handle_export_step_subset(body):
    source=get_design();original=_bh.app.activeDocument
    mgr=adsk.fusion.TemporaryBRepManager.get();copies=[]
    for occ in source.rootComponent.occurrences:
        if occ.component.name not in body['include']:continue
        copies.append((occ.component.name,occ.transform2.copy(),[(b.name,mgr.copy(b)) for b in occ.component.bRepBodies]))
    temp=None
    try:
        temp=_bh.app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        design=adsk.fusion.Design.cast(_bh.app.activeProduct)
        design.designIntent=adsk.fusion.DesignIntentTypes.HybridDesignIntentType
        design.designType=adsk.fusion.DesignTypes.DirectDesignType
        for name,matrix,bodies in copies:
            occ=design.rootComponent.occurrences.addNewComponent(matrix);occ.component.name=name
            for bname,b in bodies:occ.component.bRepBodies.add(b).name=bname
        options=design.exportManager.createSTEPExportOptions(body['path'])
        ok=design.exportManager.execute(options)
        return {'success':ok,'path':body['path'],'components':len(copies)}
    finally:
        if temp:temp.close(False)
        original.activate()

MECHANICAL_REVIEW_ROUTES={'/mechanical_export_step':handle_export_step_subset,'/mechanical_fillet':handle_component_fillet,'/mechanical_rigid':handle_rigid,'/mechanical_shift_sketch':handle_shift_sketch,'/mechanical_live_geometry':handle_live_geometry,'/mechanical_check_pose':handle_check_pose,'/mechanical_joint_at':handle_joint_at,'/mechanical_display':handle_review_display,'/mechanical_drive':handle_joint_drive}
