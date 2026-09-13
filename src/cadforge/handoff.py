"""Traceable prototype exports; integrity metadata is not manufacturing approval."""
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
import math
import cadquery as cq


def exact_bounds(shape):
    """Measure CAD surfaces, unaffected by an export's cached triangulation."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    bounds=Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.wrapped,bounds,False,False)
    return cq.BoundBox(bounds)


def write_handoff(result, exports, output_dir):
    out=Path(output_dir).resolve()
    parts_dir=out/'parts';parts_dir.mkdir(parents=True,exist_ok=True)
    files={}
    def inventory(path):
        path=Path(path).resolve()
        relative=path.relative_to(out).as_posix()
        data=path.read_bytes()
        files[relative]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
        return relative
    for path in exports.values():inventory(path)
    from .regeneration import write_regeneration
    regeneration_files=[inventory(path) for path in write_regeneration(out)]
    parts=[]
    for name,shape in result.parts.items():
        if not re.fullmatch(r'[A-Za-z0-9_-]+',name):
            raise ValueError('Part name must be a safe export identifier')
        paths={}
        for extension in ('step','stl'):
            path=parts_dir/f'{name}.{extension}'
            cq.exporters.export(shape,str(path))
            paths[extension]=inventory(path)
        bounds=exact_bounds(shape)
        parts.append({'name':name,'exports':paths,'volume_mm3':shape.Volume(),
                      'solid_count':len(shape.Solids()),
                      'bounds_mm':[[bounds.xmin,bounds.ymin,bounds.zmin],[bounds.xmax,bounds.ymax,bounds.zmax]]})
    manifest={'version':1,'units':'mm','production_ready':False,
              'process':'MJF PA12, provisional; supplier qualification required',
              'specification':result.spec.model_dump(),'parts':parts,'files':files,
              'regeneration_files':regeneration_files,
              'fabrication_inputs':'Use named part STEP/STL pairs. Combined assembly mesh is for visualization only.',
              'limitations':['Hashes identify these exported bytes, not independently approved geometry.',
                             'Physical fit, process capability and production release remain unqualified.']}
    errors=_manifest_errors(manifest)
    if errors:raise ValueError('Incomplete manufacturing handoff: '+json.dumps(errors))
    path=out/'manufacturing-manifest.json'
    path.write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
    return str(path)


def _manifest_errors(data):
    """Validate inventory structure before interpreting any file identity claim."""
    errors=[]
    def reject(reason):errors.append({'path':'manufacturing-manifest.json','reason':reason})
    if not isinstance(data,dict):
        reject('manifest must be an object');return errors
    if type(data.get('version')) is not int or data['version']!=1:reject('unsupported manifest version')
    if data.get('units')!='mm':reject('manifest units must be mm')
    if data.get('production_ready') is not False:reject('prototype manifest cannot claim production approval')
    if not isinstance(data.get('specification'),dict) or not data['specification']:reject('missing editable specification')
    files=data.get('files')
    if not isinstance(files,dict) or not files:
        reject('file inventory must be nonempty');files={}
    for relative,expected in files.items():
        if (not isinstance(relative,str) or not relative or '\\' in relative
                or PurePosixPath(relative).is_absolute() or '..' in PurePosixPath(relative).parts
                or PurePosixPath(relative).as_posix()!=relative):
            reject('invalid package-relative path');continue
        if (not isinstance(expected,dict) or type(expected.get('bytes')) is not int or expected['bytes']<=0
                or not isinstance(expected.get('sha256'),str) or not re.fullmatch('[0-9a-f]{64}',expected['sha256'])):
            reject('invalid file identity metadata for '+relative)
    if not any(str(name).endswith('.py') for name in files):reject('editable Python source is not inventoried')
    if 'regeneration_files' in data:
        recipe=data['regeneration_files']
        if not isinstance(recipe,list) or not recipe or any(not isinstance(p,str) or p not in files for p in recipe):
            reject('Regeneration snapshot missing from file inventory')
    if 'review_evidence' in data:
        evidence=data['review_evidence']
        if not isinstance(evidence,dict) or set(evidence)!={'prebuild_contract','prebuild_layout','engineering','geometry_screen'}:
            reject('review evidence requires all four report roles')
        elif any(not isinstance(relative,str) or relative not in files for relative in evidence.values()):
            reject('review evidence is missing from file inventory')
        elif len(set(evidence.values()))!=4:reject('review evidence roles require distinct files')
    parts=data.get('parts')
    if not isinstance(parts,list) or not parts:
        reject('part inventory must be nonempty');parts=[]
    names=set();references=set()
    for part in parts:
        if not isinstance(part,dict):reject('part must be an object');continue
        name=part.get('name')
        if not isinstance(name,str) or not re.fullmatch('[A-Za-z0-9_-]+',name) or name in names:
            reject('invalid or duplicate part name')
        else:names.add(name)
        exports=part.get('exports')
        if not isinstance(exports,dict) or set(exports)!={'step','stl'}:
            reject('each part requires STEP and STL exports');continue
        for kind,relative in exports.items():
            if not isinstance(relative,str) or relative not in files or not relative.endswith('.'+kind):
                reject('part export missing from inventory or wrong format')
            elif relative in references:reject('part exports must have distinct paths')
            else:references.add(relative)
        volume=part.get('volume_mm3')
        if type(volume) not in (int,float) or not math.isfinite(volume) or volume<=0:reject('invalid part volume')
        if type(part.get('solid_count')) is not int or part['solid_count']<=0:reject('invalid solid count')
        bounds=part.get('bounds_mm')
        if (not isinstance(bounds,list) or len(bounds)!=2
                or any(not isinstance(row,list) or len(row)!=3 for row in bounds)
                or any(type(x) not in (int,float) or not math.isfinite(x) for row in bounds for x in row)
                or any(bounds[0][i]>=bounds[1][i] for i in range(3))):reject('invalid part bounds')
    return errors


def inventory_review_evidence(manifest_path, evidence):
    """Append completed review artifacts without claiming review approval.

    Geometry screening precedes this final inventory and does not hash itself.
    The completed manifest hashes the reports; reports never hash this manifest.
    """
    import uuid
    path=Path(manifest_path).resolve()
    if not verify_handoff(path)['integrity_passed']:
        raise ValueError('Cannot attach evidence to a failed package inventory')
    data=json.loads(path.read_text(),object_pairs_hook=_unique_object)
    roles={}
    for role,source in evidence.items():
        source=Path(source).resolve()
        relative=source.relative_to(path.parent).as_posix()
        if source==path:raise ValueError('Manifest cannot inventory itself')
        contents=source.read_bytes()
        identity={'bytes':len(contents),'sha256':hashlib.sha256(contents).hexdigest()}
        if relative in data['files'] and data['files'][relative]!=identity:
            raise ValueError('Evidence cannot replace an existing file identity')
        data['files'][relative]=identity;roles[role]=relative
    data['review_evidence']=roles
    errors=_manifest_errors(data)
    if errors:raise ValueError('Incomplete review evidence: '+json.dumps(errors))
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temporary.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
    temporary.replace(path)


def _unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('Duplicate JSON key: '+key)
        result[key]=value
    return result


def verify_handoff(manifest_path):
    """Check completeness and portable byte identity, never execute CAD source.

    This does not authenticate the manifest or independently qualify geometry.
    """
    path=Path(manifest_path).resolve()
    try:
        data=json.loads(path.read_text(),object_pairs_hook=_unique_object)
        failures=_manifest_errors(data)
    except (OSError,ValueError) as error:
        data={};failures=[{'path':path.name,'reason':'unreadable manifest: '+str(error)}]
    files=data.get('files',{}) if isinstance(data,dict) else {}
    count=len(files) if isinstance(files,dict) else 0
    if not failures:
        for relative,expected in files.items():
            candidate=(path.parent/relative).resolve()
            if not candidate.is_relative_to(path.parent):
                failures.append({'path':relative,'reason':'path escapes package'});continue
            try:
                contents=candidate.read_bytes()
            except OSError:
                failures.append({'path':relative,'reason':'missing or unreadable file'});continue
            if len(contents)!=expected['bytes'] or hashlib.sha256(contents).hexdigest()!=expected['sha256']:
                failures.append({'path':relative,'reason':'file identity changed'})
    return {'integrity_passed':not failures,'file_count':count,
            'failures':failures,'production_ready':False}
