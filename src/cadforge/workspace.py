"""Versioned imported CAD mesh workspace with preview/commit/undo boundaries.

STL edits are faceted mesh operations, not reconstructed parametric feature trees.
"""
from __future__ import annotations
import json
import hashlib
import math
import re
import shutil
import threading
import uuid
from pathlib import Path
import numpy as np
import trimesh

MAX_BYTES=50*1024*1024
MAX_FACES=500_000
MAX_PARTS=256


def _identifier(value):
    if not isinstance(value,str) or not re.fullmatch(r'[a-f0-9]{32}',value):
        raise ValueError('Invalid workspace identifier')
    return value


def _write(path,data):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
    temporary.replace(path)


def _number(value,positive=False):
    number=float(value)
    if not math.isfinite(number) or abs(number)>10000 or (positive and number<=0):
        raise ValueError('Dimensions must be finite, within 10000 mm and positive where required')
    return number


def _vector(value,positive=False):
    if not isinstance(value,(list,tuple)) or len(value)!=3:
        raise ValueError('Expected three dimensions')
    return [_number(v,positive) for v in value]


def _valid(mesh):
    return bool(len(mesh.faces)>0 and len(mesh.faces)<=MAX_FACES and np.isfinite(mesh.vertices).all() and mesh.is_watertight and mesh.is_winding_consistent and mesh.volume>1e-8)


class PythonWorkspace:
    def __init__(self,root,region_learning_path=None):
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True)
        self._lock=threading.RLock()
        from .edit_learning import DEFAULT_STORE
        self.region_learning_path=Path(region_learning_path) if region_learning_path is not None else DEFAULT_STORE

    def _folder(self,session_id):
        folder=self.root/_identifier(session_id)
        if not (folder/'session.json').is_file():raise ValueError('Unknown workspace session')
        return folder

    def _document(self,session_id):
        return json.loads((self._folder(session_id)/'session.json').read_text())

    def _part(self,mesh,part_id,name,directory):
        destination=directory/(part_id+'.stl')
        mesh.export(destination)
        return {'id':part_id,'name':name,'bounds':mesh.bounds.tolist(),'triangles':len(mesh.faces),
                'watertight':bool(mesh.is_watertight),'volume_mm3':float(mesh.volume),
                'stl_path':str(destination.resolve())}

    def import_file(self,path,units='mm'):
        with self._lock:
            source=Path(path)
            if not source.is_file() or source.stat().st_size>MAX_BYTES:
                raise ValueError('Import must be an existing file no larger than 50 MiB')
            if units not in ('mm','cm','in'):
                raise ValueError('Explicit units must be mm, cm or in')
            extension=source.suffix.lower()
            if extension not in ('.stl','.step','.stp'):
                raise ValueError('Only STL and STEP imports are supported')
            if extension=='.stl':
                loaded=trimesh.load(source,force='mesh',process=True)
                if len(loaded.faces)>MAX_FACES:raise ValueError('Import exceeds 500000 triangles')
                meshes=list(loaded.split(only_watertight=False))
            else:
                # OpenCascade converts STEP's declared length units to millimeters.
                if units!='mm':raise ValueError('STEP importer normalizes declared file units to mm; select mm')
                import cadquery as cq
                shape=cq.importers.importStep(str(source)).val()
                solids=shape.Solids()
                if not solids:raise ValueError('STEP contains no solid bodies')
                if len(solids)>MAX_PARTS:raise ValueError('Too many STEP bodies')
                meshes=[]
                for solid in solids:
                    vertices,faces=solid.tessellate(.05,.15)
                    mesh=trimesh.Trimesh(vertices=[v.toTuple() for v in vertices],faces=faces,process=True)
                    mesh.fix_normals();meshes.append(mesh)
            if not meshes or len(meshes)>MAX_PARTS or sum(len(m.faces) for m in meshes)>MAX_FACES:
                raise ValueError('Import is empty or exceeds part/triangle limits')
            scale={'mm':1.,'cm':10.,'in':25.4}[units]
            for mesh in meshes:
                mesh.apply_scale(scale)
                if not np.isfinite(mesh.vertices).all() or np.max(np.abs(mesh.vertices))>100000:
                    raise ValueError('Nonfinite or out-of-range imported coordinates')
            identifier=uuid.uuid4().hex;version=uuid.uuid4().hex
            folder=self.root/identifier;directory=folder/'versions'/version;directory.mkdir(parents=True)
            original=folder/('original'+extension);shutil.copyfile(source,original)
            parts=[self._part(m,uuid.uuid4().hex,f'Part {i+1}',directory) for i,m in enumerate(meshes)]
            state={'id':identifier,'name':source.name,'revision':0,'version':version,'parent_version':None,
                'parts':parts,'units':'mm','source_units':units,'original_path':str(original),
                'history':[{'action':'import','version':version,'source_name':source.name}],
                'limitations':['Imported topology is a faceted mesh; original STEP is retained separately.','Geometry checks do not establish load capacity or manufacturing readiness.']}
            _write(directory/'state.json',state);_write(folder/'session.json',state)
            return state

    def state(self,session_id):
        with self._lock:return self._document(session_id)

    def preview(self,session_id,command,selection=None,*,expected_revision=None,dimension_rule=None):
        with self._lock:
            state=self._document(session_id);folder=self._folder(session_id)
            if expected_revision is not None and state['revision']!=expected_revision:
                raise ValueError('Workspace changed while planning; refresh and request a new preview')
            preview_id=uuid.uuid4().hex;directory=folder/'previews'/preview_id;directory.mkdir(parents=True)
            selection=selection or {};checks=[];error=None;parts=[]
            region_outcome=None
            record={'preview_id':preview_id,'session_id':session_id,'base_revision':state['revision'],'base_version':state['version'],
                'command':command,'selection':selection,'accepted':False,'parts':parts,'checks':checks}
            if dimension_rule is not None:
                record['dimension_rule']=json.loads(json.dumps(dimension_rule,allow_nan=False))
            try:
                if not isinstance(command,dict) or not isinstance(selection,dict):raise ValueError('Command and selection must be objects')
                op=command.get('op')
                allowed={'translate','resize','resize_preserving_holes','add_box','add_cylinder','cut_cylinder','drill_blind_hole','drill_surface_hole','counterbore'}
                if op not in allowed:raise ValueError('Unsupported edit operation')
                part_id=selection.get('part_id');region=selection.get('region')
                selected=next((p for p in state['parts'] if p['id']==part_id),None)
                if part_id is not None and selected is None:raise ValueError('Unknown selected part')
                if op in ('translate','resize','resize_preserving_holes','cut_cylinder','drill_blind_hole','drill_surface_hole','counterbore') and selected is None:raise ValueError('Select one part for this operation')
                mesh=trimesh.load(selected['stl_path'],force='mesh',process=True) if selected else None
                if mesh is not None and not _valid(mesh):raise ValueError('Selected part must have positive, watertight, consistently oriented geometry before editing')
                if region is None:
                    from .execution_budget import charge
                    charge('cad_candidates')
                if region is not None:
                    if op not in ('translate','resize'):raise ValueError('Region selection supports only translate and resize')
                    if not isinstance(region,dict):raise ValueError('Invalid selection region')
                    _vector(region['min']);_vector(region['max'])
                    if command.get('axis') not in ('x','y','z'):raise ValueError('Axis must be x, y or z')
                    _number(command['amount_mm']) if op=='translate' else _number(command['target_mm'],True)
                    from .region_edit import deform_region
                    from .edit_learning import recommend,validator_context
                    try:
                        hint=recommend(command,path=self.region_learning_path)
                    except Exception as retrieval_error:
                        hint={'strategy':None,'skill_id':None,'context':validator_context()}
                        record['learning_retrieval_error']=f'{type(retrieval_error).__name__}: {retrieval_error}'
                    record['learning_hint']=hint
                    record['source_mesh_sha256']=hashlib.sha256(Path(selected['stl_path']).read_bytes()).hexdigest()
                    effective_command={k:v for k,v in command.items() if k!='learned_strategy'}
                    if hint['strategy']:effective_command['learned_strategy']=hint['strategy']
                    region_outcome={'mesh':mesh,'command':command,'region':region,'hint':hint,'trials':[]}
                    record['effective_command']=effective_command
                    changed,region_checks=deform_region(mesh.copy(),effective_command,region)
                    region_outcome['trials']=next(c['detail'] for c in region_checks if c['name']=='repair_trials')
                    checks.extend(region_checks)
                elif op=='counterbore':
                    from .protected_edit import _recognized_straight
                    try:
                        _recognized_straight(mesh)
                    except ValueError:
                        from .profile_counterbore import counterbore
                    else:
                        from .counterbore import counterbore
                    changed,feature_checks,feature=counterbore(mesh,
                        _number(command['radius_mm'],True),_number(command['depth_mm'],True),
                        _vector(command['entry']),command.get('direction',-1))
                    checks.extend(feature_checks)
                    record['created_features']=[feature]
                elif op=='drill_surface_hole':
                    from .surface_hole import drill_surface_hole
                    changed,surface_checks,feature=drill_surface_hole(mesh,
                        _number(command['radius_mm'],True),_number(command['depth_mm'],True),
                        _vector(command['entry']),_vector(command['normal']))
                    checks.extend(surface_checks)
                    record['created_features']=[feature]
                elif op=='drill_blind_hole':
                    from .blind_hole import drill_blind_hole
                    changed,drill_checks,feature=drill_blind_hole(mesh,
                        _number(command['radius_mm'],True),_number(command['depth_mm'],True),
                        _vector(command['entry']),command.get('direction'))
                    checks.extend(drill_checks)
                    record['created_features']=[feature]
                elif op=='resize_preserving_holes':
                    from .axial_protected_edit import resize_preserving_axial_holes
                    changed,protected_checks,features=resize_preserving_axial_holes(
                        mesh,command.get('axis'),_number(command['target_mm'],True),
                        min_wall_mm=_number(command.get('min_wall_mm',1.),True))
                    checks.extend(protected_checks)
                    record['protected_features']=features
                elif op in ('translate','resize'):
                    axis={'x':0,'y':1,'z':2}.get(command.get('axis'))
                    if axis is None:raise ValueError('Axis must be x, y or z')
                    changed=mesh.copy()
                    if op=='translate':
                        offset=np.zeros(3);offset[axis]=_number(command['amount_mm']);changed.apply_translation(offset)
                    else:
                        target=_number(command['target_mm'],True);extent=mesh.extents[axis]
                        if extent<=1e-8:raise ValueError('Selected axis has zero extent')
                        vertices=changed.vertices.copy();center=mesh.bounds[:,axis].mean()
                        vertices[:,axis]=(vertices[:,axis]-center)*target/extent+center;changed.vertices=vertices
                    checks.append({'name':'selection.whole_part','passed':True,'detail':'Unselected parts are copied unchanged'})
                else:
                    center=_vector(command.get('center',[0,0,0]))
                    if op=='add_box':primitive=trimesh.creation.box(extents=_vector(command['size'],True))
                    else:primitive=trimesh.creation.cylinder(radius=_number(command['radius_mm'],True),height=_number(command['height_mm'],True),sections=64)
                    primitive.apply_translation(center)
                    if mesh is None:changed=primitive
                    elif op=='cut_cylinder':changed=trimesh.boolean.difference([mesh,primitive],engine='manifold')
                    else:changed=trimesh.boolean.union([mesh,primitive],engine='manifold')
                    if changed is None or len(changed.faces)==0:raise ValueError('Boolean operation removed all material')
                    if op=='cut_cylinder':
                        removed=mesh.volume-changed.volume
                        checks.append({'name':'boolean.removed_material','passed':bool(removed>1e-7),'detail':f'Removed {removed:.6g} mm3'})
                    elif mesh is not None:
                        checks.append({'name':'boolean.added_material','passed':bool(changed.volume-mesh.volume>1e-7),'detail':'Union must add nonzero material'})
                checks.append({'name':'geometry.valid_mesh','passed':_valid(changed),'detail':'Positive volume, finite vertices, watertight and consistent face winding'})
                total_faces=sum(p['triangles'] for p in state['parts'] if p['id']!=part_id)+len(changed.faces)
                checks.append({'name':'resource.triangles','passed':total_faces<=MAX_FACES,'detail':'Workspace limit 500000 triangles'})
                if not all(c['passed'] for c in checks):raise ValueError('Candidate failed geometry or invariant checks')
                for part in state['parts']:
                    if part['id']==part_id:parts.append(self._part(changed,part_id,part['name'],directory))
                    else:
                        destination=directory/(part['id']+'.stl');shutil.copyfile(part['stl_path'],destination)
                        parts.append({**part,'stl_path':str(destination.resolve())})
                if selected is None:
                    if len(parts)>=MAX_PARTS:raise ValueError('Workspace part limit reached')
                    parts.append(self._part(changed,uuid.uuid4().hex,'Added '+op.removeprefix('add_'),directory))
                record['accepted']=True
            except Exception as exc:
                error=f'{type(exc).__name__}: {exc}'
                from .execution_budget import BudgetExceeded
                if isinstance(exc,BudgetExceeded):record['budget_exhausted']=exc.kind
                if hasattr(exc,'checks'):checks.extend(exc.checks)
                if hasattr(exc,'trials'):record['repair_trials']=exc.trials
                if region_outcome is not None and hasattr(exc,'trials'):region_outcome['trials']=exc.trials
                checks.append({'name':'edit.accepted','passed':False,'detail':error})
                # Display original state on failed previews; no active geometry changes.
                record['parts']=state['parts']
            record['error']=error
            if region_outcome is not None and not record.get('budget_exhausted'):
                from .edit_learning import record_executed
                try:
                    record['learning']=record_executed(**region_outcome,accepted=record['accepted'],
                        session_id=session_id,preview_id=preview_id,error=error,path=self.region_learning_path)
                except Exception as learning_error:
                    record['learning']={'status':'audit_failed','attempts':len(region_outcome['trials']),
                        'narrative':'Geometry outcome is retained, but persistent learning audit failed.',
                        'error':f'{type(learning_error).__name__}: {learning_error}'}
                record['repair_trials']=region_outcome['trials']
            elif record.get('budget_exhausted'):
                record['learning']={'status':'budget_censored','narrative':'The evaluation budget stopped this edit. Retained trials are not evidence that unattempted repairs failed.'}
            _write(directory/'preview.json',record)
            return record

    def retry_learning(self,session_id,preview_id):
        """Reconcile local retained trials only; never execute geometry or archives."""
        with self._lock:
            from .edit_learning import record_executed,validator_context
            folder=self._folder(session_id)
            path=folder/'previews'/_identifier(preview_id)/'preview.json'
            if not path.is_file():raise ValueError('No locally executed preview to recover')
            record=json.loads(path.read_text())
            if record.get('session_id')!=session_id or record.get('preview_id')!=preview_id:
                raise ValueError('Preview identity mismatch')
            hint=record.get('learning_hint')
            if not hint or hint.get('context')!=validator_context():
                raise ValueError('Validator context changed or recovery metadata missing')
            region=record.get('selection',{}).get('region')
            if not region or 'repair_trials' not in record:
                raise ValueError('No retained region trials to recover')
            source=folder/'versions'/_identifier(record.get('base_version'))/(_identifier(record['selection'].get('part_id'))+'.stl')
            if not source.resolve().is_relative_to(folder.resolve()) or not source.is_file():
                raise ValueError('Original source mesh is unavailable')
            if hashlib.sha256(source.read_bytes()).hexdigest()!=record.get('source_mesh_sha256'):
                raise ValueError('Original source mesh changed')
            mesh=trimesh.load(source,force='mesh',process=True)
            receipt=record_executed(mesh,record['command'],region,record['repair_trials'],record['accepted'],
                session_id=session_id,preview_id=preview_id,hint=hint,error=record.get('error'),path=self.region_learning_path)
            record['learning']=receipt;record['learning_recovered']=True
            _write(path,record)
            return receipt

    def preview_sequence(self,session_id,steps,*,expected_revision=None,invariants=None):
        from .composition import preview_sequence
        return preview_sequence(self,session_id,steps,expected_revision,invariants=invariants)

    def commit(self,session_id,preview_id):
        with self._lock:
            folder=self._folder(session_id);state=self._document(session_id)
            record_path=folder/'previews'/_identifier(preview_id)/'preview.json'
            if not record_path.is_file():raise ValueError('Unknown preview')
            record=json.loads(record_path.read_text())
            if not record['accepted']:raise ValueError('Cannot commit a rejected preview')
            if record['base_revision']!=state['revision']:raise ValueError('Preview is stale; generate a new preview')
            version=uuid.uuid4().hex;directory=folder/'versions'/version;directory.mkdir(parents=True)
            parts=[]
            for part in record['parts']:
                target=directory/(part['id']+'.stl');shutil.copyfile(part['stl_path'],target)
                parts.append({**part,'stl_path':str(target.resolve())})
            updated={**state,'revision':state['revision']+1,'version':version,'parent_version':state['version'],
                'parts':parts,'history':state['history']+[{'action':'commit','version':version,'parent':state['version'],
                    'preview_id':preview_id,'command':record['command'],'selection':record['selection'],'checks':record['checks'],
                    **{key:record[key] for key in ('created_features','protected_features','learning','effective_command','repair_trials','step_outcomes','learning_scope','invariants','dimension_rule') if key in record}}]}
            _write(directory/'state.json',updated);_write(folder/'session.json',updated)
            return updated

    def undo(self,session_id):
        with self._lock:
            folder=self._folder(session_id);state=self._document(session_id)
            parent=state.get('parent_version')
            if parent is None:raise ValueError('No committed edit to undo')
            prior=json.loads((folder/'versions'/_identifier(parent)/'state.json').read_text())
            restored={**prior,'revision':state['revision']+1,
                'history':state['history']+[{'action':'undo','from':state['version'],'to':parent}]}
            _write(folder/'session.json',restored)
            return restored

    def export_project(self,session_id):
        from .project_archive import export_project
        with self._lock:return export_project(self,session_id)

    def import_project(self,path):
        from .project_archive import import_project
        with self._lock:return import_project(self,path)

    def export_path(self,session_id,part_id=None):
        with self._lock:
            state=self._document(session_id)
            if part_id is not None:
                part=next((p for p in state['parts'] if p['id']==part_id),None)
                if part is None:raise ValueError('Unknown part')
                return Path(part['stl_path'])
            meshes=[trimesh.load(p['stl_path'],force='mesh') for p in state['parts']]
            path=self._folder(session_id)/'versions'/state['version']/'assembly.stl'
            if not path.exists():trimesh.util.concatenate(meshes).export(path)
            return path
