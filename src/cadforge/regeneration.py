"""Package the production recipe source and its installed dependency versions."""
import importlib.metadata as metadata
import json
from pathlib import Path
import platform
import shutil
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

RECIPE_MODULES=('__init__.py','schema.py','geometry.py','production_geometry.py',
                'operations.py','handoff.py','handoff_geometry.py','regeneration.py','camera_interconnect.py')


def write_regeneration(directory):
    out=Path(directory)/'regeneration';source=out/'src/cadforge';source.mkdir(parents=True,exist_ok=True)
    files=[]
    for name in RECIPE_MODULES:
        target=source/name;shutil.copyfile(Path(__file__).with_name(name),target);files.append(target)
    pending=['cadquery','pydantic','trimesh','numpy','scipy','packaging'];versions={}
    while pending:
        name=canonicalize_name(pending.pop())
        if name in versions:continue
        dist=metadata.distribution(name);versions[name]=dist.version
        for raw in dist.requires or ():
            requirement=Requirement(raw)
            if requirement.marker is None or requirement.marker.evaluate({'extra':''}):pending.append(requirement.name)
    lock=out/'requirements.txt';lock.write_text(''.join(f'{k}=={v}\n' for k,v in sorted(versions.items())));files.append(lock)
    environment=out/'environment.json';environment.write_text(json.dumps({
        'python':platform.python_version(),'system':platform.system(),'machine':platform.machine(),
        'scope':'Installed Python dependency versions for this platform; binaries, system libraries and build hashes are not bundled.'},indent=2)+'\n');files.append(environment)
    instructions=out/'README.md';instructions.write_text('''# Regenerate the packaged recipe

Use a separate environment with the Python version and platform recorded in environment.json.
Install requirements.txt. From the package directory, set PYTHONPATH to regeneration/src and run design.py.
Edit the literal SPEC in a copy of design.py to change dimensions; output goes to regenerated/.
The recipe source is bundled and inventoried, so an installed CADForge version is not required.

This records dependency versions, not binary wheel hashes or a complete OS image.
Package integrity is not code authentication. Review source before executing a package from another party.
Regenerated geometry must be rechecked; physical production readiness is never inferred.
''');files.append(instructions)
    return files
