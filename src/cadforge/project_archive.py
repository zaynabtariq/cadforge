"""Portable inert JSON CAD projects. Hashes detect corruption, not authorship.

Only the active version ancestry is portable; history text retains abandoned
branch events but abandoned branch geometry and uncommitted previews are omitted.
"""
from __future__ import annotations
import base64
import copy
import hashlib
import io
import json
import shutil
import uuid
from pathlib import Path
import numpy as np
import trimesh

MAX_ARCHIVE_BYTES=100*1024*1024
MAX_VERSIONS=100


def _reject_constant(value):
    raise ValueError('Nonfinite JSON is forbidden')


def _object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('Duplicate JSON key')
        result[key]=value
    return result


def _read(path):
    path=Path(path)
    if not path.is_file() or path.stat().st_size>MAX_ARCHIVE_BYTES:raise ValueError('Project exceeds 100 MiB or is missing')
    try:
        data=json.loads(path.read_text(),parse_constant=_reject_constant,object_pairs_hook=_object)
        # Reject overflow such as 1e999 as well as literal NaN.
        json.dumps(data,allow_nan=False)
        return data
    except (RecursionError,UnicodeError,OverflowError) as error:raise ValueError('Invalid project JSON') from error


def _inside(path,root):
    path=Path(path).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():raise ValueError('Archive source path is outside workspace or missing')
    return path


def export_project(workspace,session_id):
    from .workspace import _identifier
    folder=workspace._folder(session_id);current=workspace._document(session_id)
    blobs={};total=0
    def blob(path):
        nonlocal total
        path=_inside(path,folder)
        size=path.stat().st_size
        if size>MAX_ARCHIVE_BYTES:raise ValueError('Project exceeds 100 MiB')
        payload=path.read_bytes();digest=hashlib.sha256(payload).hexdigest()
        if digest not in blobs:
            total+=4*((len(payload)+2)//3)
            if total>MAX_ARCHIVE_BYTES:raise ValueError('Project exceeds 100 MiB')
            blobs[digest]=base64.b64encode(payload).decode('ascii')
        return digest
    def portable(state):
        result=copy.deepcopy(state);result.pop('original_path',None)
        for part in result['parts']:part['blob']=blob(part.pop('stl_path'))
        return result
    versions={};version=current['version']
    while version is not None:
        _identifier(version)
        if version in versions:raise ValueError('Cyclic version graph')
        if len(versions)>=MAX_VERSIONS:raise ValueError('Project exceeds 100 versions')
        state=_read(_inside(folder/'versions'/version/'state.json',folder))
        if state['version']!=version:raise ValueError('Version snapshot mismatch')
        versions[version]=portable(state);version=state.get('parent_version')
    original=_inside(current['original_path'],folder)
    document={'format':'cadforge.project','format_version':1,'current':portable(current),'versions':versions,
              'original':{'extension':original.suffix.lower(),'blob':blob(original)},'blobs':blobs}
    payload=json.dumps(document,allow_nan=False,separators=(',',':')).encode()
    if len(payload)>MAX_ARCHIVE_BYTES:raise ValueError('Project exceeds 100 MiB')
    destination=folder/'project.cadforge';temporary=folder/'project.cadforge.tmp'
    temporary.write_bytes(payload);temporary.replace(destination)
    return destination


def import_project(workspace,path):
    from .workspace import _identifier,_valid,MAX_FACES,MAX_PARTS,_write
    archive=_read(path)
    if not isinstance(archive,dict) or archive.get('format')!='cadforge.project' or archive.get('format_version')!=1:
        raise ValueError('Unsupported project format')
    versions=archive.get('versions');current=archive.get('current');blobs=archive.get('blobs');original=archive.get('original')
    if not isinstance(versions,dict) or not 1<=len(versions)<=MAX_VERSIONS:raise ValueError('Invalid version count')
    if not isinstance(blobs,dict) or not isinstance(original,dict) or not isinstance(current,dict):raise ValueError('Invalid project objects')
    if original.get('extension') not in ('.stl','.step','.stp'):raise ValueError('Invalid original file type')
    decoded={};decoded_size=0
    for digest,encoded in blobs.items():
        if not isinstance(digest,str) or len(digest)!=64 or not isinstance(encoded,str):raise ValueError('Invalid blob')
        try:payload=base64.b64decode(encoded,validate=True)
        except Exception as error:raise ValueError('Invalid base64 blob') from error
        decoded_size+=len(payload)
        if decoded_size>MAX_ARCHIVE_BYTES or hashlib.sha256(payload).hexdigest()!=digest:raise ValueError('Blob hash or size mismatch')
        decoded[digest]=payload
    if not isinstance(original.get('blob'),str) or original['blob'] not in decoded:raise ValueError('Missing original blob')
    references={original['blob']};meshes={};source_ids=set()
    def validate_state(state):
        if not isinstance(state,dict):raise ValueError('Invalid state')
        for key in ('id','version'):_identifier(state.get(key));source_ids.add(state[key])
        parent=state.get('parent_version')
        if parent is not None:_identifier(parent)
        if type(state.get('revision')) is not int or state['revision']<0:raise ValueError('Invalid revision')
        if state.get('units')!='mm' or state.get('source_units') not in ('mm','cm','in'):raise ValueError('Invalid project units')
        if not isinstance(state.get('history'),list) or not isinstance(state.get('name'),str):raise ValueError('Invalid project metadata')
        if 'original_path' in state:raise ValueError('Archive must not contain original filesystem paths')
        parts=state.get('parts')
        if not isinstance(parts,list) or not 1<=len(parts)<=MAX_PARTS:raise ValueError('Invalid parts')
        seen=set();faces=0
        for part in parts:
            if not isinstance(part,dict) or 'stl_path' in part:raise ValueError('Archive must not contain part filesystem paths')
            identifier=_identifier(part.get('id'))
            if identifier in seen:raise ValueError('Duplicate part ID')
            seen.add(identifier);source_ids.add(identifier)
            digest=part.get('blob')
            if not isinstance(digest,str) or digest not in decoded:raise ValueError('Missing mesh blob')
            references.add(digest)
            if digest not in meshes:
                mesh=trimesh.load(io.BytesIO(decoded[digest]),file_type='stl',force='mesh',process=True)
                if not isinstance(mesh,trimesh.Trimesh) or not _valid(mesh) or np.max(np.abs(mesh.vertices))>100000:
                    raise ValueError('Archive contains invalid mesh')
                meshes[digest]=mesh
            faces+=len(meshes[digest].faces)
        if faces>MAX_FACES:raise ValueError('Version exceeds triangle limit')
    for key,state in versions.items():
        _identifier(key);validate_state(state)
        if state['version']!=key:raise ValueError('Version key mismatch')
    validate_state(current)
    visited=set();version=current['version']
    while version is not None:
        if version in visited or version not in versions:raise ValueError('Cyclic or missing version parent')
        visited.add(version);version=versions[version].get('parent_version')
    if visited!=set(versions):raise ValueError('Archive contains disconnected versions')
    snapshot=versions[current['version']]
    if current.get('parent_version')!=snapshot.get('parent_version') or current['parts']!=snapshot['parts']:
        raise ValueError('Current geometry differs from version snapshot')
    if len({state['id'] for state in [current,*versions.values()]})!=1:raise ValueError('Mixed session identities')
    if set(decoded)!=references:raise ValueError('Unreferenced archive blobs')
    # The retained original is inert. STL originals are parsed for finite geometry;
    # STEP bytes retain their header and are never executed or imported as code.
    raw=decoded[original['blob']]
    if original['extension']=='.stl':
        original_mesh=trimesh.load(io.BytesIO(raw),file_type='stl',force='mesh',process=True)
        if not len(original_mesh.faces) or len(original_mesh.faces)>MAX_FACES or not np.isfinite(original_mesh.vertices).all():raise ValueError('Invalid original STL')
    elif b'ISO-10303-21;' not in raw[:4096].upper() or b'END-ISO-10303-21;' not in raw[-4096:].upper():raise ValueError('Invalid original STEP envelope')
    identifier=uuid.uuid4().hex;folder=workspace.root/identifier
    staging=workspace.root/('.import-'+uuid.uuid4().hex)
    mapping={value:uuid.uuid4().hex for value in source_ids};mapping[current['id']]=identifier
    def remap(value):
        if isinstance(value,str):return mapping.get(value,value)
        if isinstance(value,list):return [remap(item) for item in value]
        if isinstance(value,dict):return {key:remap(item) for key,item in value.items()}
        return value
    def restore(state):
        result=remap(copy.deepcopy(state));result['history_trust']='imported-unverified';result['original_path']=str(folder/('original'+original['extension']))
        for part in result['parts']:
            digest=part.pop('blob');mesh=meshes[digest]
            relative=Path('versions')/result['version']/(part['id']+'.stl')
            target=staging/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(decoded[digest])
            part.update(stl_path=str(folder/relative),bounds=mesh.bounds.tolist(),triangles=len(mesh.faces),watertight=bool(mesh.is_watertight),volume_mm3=float(mesh.volume))
        return result
    try:
        staging.mkdir()
        (staging/('original'+original['extension'])).write_bytes(raw)
        for state in versions.values():
            restored=restore(state);_write(staging/'versions'/restored['version']/'state.json',restored)
        restored=restore(current);_write(staging/'session.json',restored)
        staging.rename(folder)
        return restored
    except Exception:
        shutil.rmtree(staging,ignore_errors=True)
        raise
