"""Actual CalculiX/Gmsh linear-elastic nominal-study backend.

Loads and material constants are explicit inputs, never inferred certification.
"""
from dataclasses import asdict, dataclass
from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import time

@dataclass(frozen=True)
class NominalLoad:
    youngs_modulus_mpa: float
    poisson_ratio: float
    force_z_n: float
    description: str


def solver_path():
    local=Path(__file__).resolve().parents[2]/'.tools/fea/env/bin/ccx'
    selected=os.environ.get('CADFORGE_CCX') or shutil.which('ccx') or (str(local) if local.exists() else None)
    if not selected:raise RuntimeError('CalculiX unavailable; set CADFORGE_CCX or install documented local environment')
    return str(Path(selected).resolve())


def solve_cantilever(shape,output_dir,load:NominalLoad,mesh_size_mm=3,timeout_seconds=120):
    import cadquery as cq
    import gmsh
    import numpy as np
    if load.youngs_modulus_mpa<=0 or not -1<load.poisson_ratio<.5 or mesh_size_mm<=0:
        raise ValueError('Invalid elastic material or mesh size')
    out=Path(output_dir).resolve();out.mkdir(parents=True,exist_ok=True)
    started=time.monotonic();step=out/'geometry.step';cq.exporters.export(shape,str(step))
    gmsh.initialize()
    try:
        gmsh.option.setNumber('General.Terminal',0)
        gmsh.model.occ.importShapes(str(step));gmsh.model.occ.synchronize()
        volumes=[tag for dim,tag in gmsh.model.getEntities(3)]
        gmsh.model.addPhysicalGroup(3,volumes,1);gmsh.model.setPhysicalName(3,1,'EALL')
        gmsh.option.setNumber('Mesh.MeshSizeMin',mesh_size_mm)
        gmsh.option.setNumber('Mesh.MeshSizeMax',mesh_size_mm)
        gmsh.model.mesh.generate(3);gmsh.model.mesh.setOrder(2)
        gmsh.write(str(out/'mesh.inp'));gmsh.write(str(out/'mesh.msh'))
        tags,coords,_=gmsh.model.mesh.getNodes();nodes=dict(zip(map(int,tags),np.asarray(coords).reshape(-1,3)))
        types,element_tags,_=gmsh.model.mesh.getElements(3)
        element_count=sum(len(ids) for ids in element_tags)
    finally:gmsh.finalize()
    xs=[coord[0] for coord in nodes.values()];lo,hi=min(xs),max(xs)
    fixed=[n for n,p in nodes.items() if abs(p[0]-lo)<1e-6]
    tip=[n for n,p in nodes.items() if abs(p[0]-hi)<1e-6]
    if not fixed or not tip:raise RuntimeError('No nodes on prescribed clamp/tip planes')
    mesh=(out/'mesh.inp').read_text()
    if '*ELEMENT, type=C3D10' not in mesh and '*ELEMENT, TYPE=C3D10' not in mesh:
        raise RuntimeError('Expected Gmsh quadratic tetrahedral C3D10 mesh')
    def node_set(name,ids):
        return '*NSET,NSET='+name+'\n'+'\n'.join(','.join(map(str,ids[i:i+12])) for i in range(0,len(ids),12))+'\n'
    deck=mesh+'\n'+node_set('FIXED',fixed)+node_set('TIP',tip)
    deck+=f'*MATERIAL,NAME=NOMINAL\n*ELASTIC\n{load.youngs_modulus_mpa},{load.poisson_ratio}\n*SOLID SECTION,ELSET=EALL,MATERIAL=NOMINAL\n*BOUNDARY\nFIXED,1,3\n*STEP\n*STATIC\n*CLOAD\n'
    deck+=''.join(f'{node},3,{load.force_z_n/len(tip):.15g}\n' for node in tip)
    deck+='*NODE PRINT,NSET=TIP\nU\n*NODE PRINT,NSET=FIXED,TOTALS=YES\nRF\n*NODE FILE\nU\n*EL FILE\nS\n*END STEP\n'
    (out/'study.inp').write_text(deck)
    solver=solver_path();env=os.environ|{'OMP_NUM_THREADS':'1'}
    result=subprocess.run([solver,'-i','study'],cwd=out,env=env,capture_output=True,text=True,timeout=timeout_seconds)
    (out/'solver.log').write_text(result.stdout+'\n'+result.stderr)
    if result.returncode or '*ERROR' in result.stdout or not (out/'study.dat').exists():
        raise RuntimeError(f'CalculiX solve failed; inspect {out}/solver.log')
    dat=(out/'study.dat').read_text();displacements={};section=None
    reactions=[]
    for line in dat.splitlines():
        if 'displacements (' in line:section='u';continue
        if 'forces (' in line:section='rf';continue
        fields=line.split()
        if len(fields)==4 and fields[0].isdigit():
            try:values=[float(v.replace('D','E')) for v in fields[1:]]
            except ValueError:continue
            if section=='u':displacements[int(fields[0])]=values
            elif section=='rf':reactions.append(values)
    uz=[displacements[n][2] for n in tip if n in displacements]
    if len(uz)!=len(tip):raise RuntimeError('Incomplete tip displacement output')
    reaction_z=sum(v[2] for v in reactions)
    report={'backend':'CalculiX','solver':solver,'solver_version':subprocess.run([solver,'-v'],capture_output=True,text=True).stdout.strip(),
      'mesher_version':gmsh.__version__,'element_type':'C3D10','node_count':len(nodes),'element_count':element_count,
      'mesh_size_mm':mesh_size_mm,'fixed_node_count':len(fixed),'loaded_node_count':len(tip),
      'mean_tip_displacement_z_mm':float(np.mean(uz)),'max_abs_tip_displacement_z_mm':float(max(abs(u) for u in uz)),
      'reaction_z_n':reaction_z,'force_balance_error_n':abs(reaction_z+load.force_z_n),
      'elapsed_seconds':time.monotonic()-started,'nominal_load':asdict(load),'engineering_ready':False,
      'boundary_conditions':'Entire xmin face fixed XYZ; total Z force equally divided over xmax face nodes.',
      'limitations':['Synthetic comparison load and homogeneous isotropic linear elasticity only.',
        'Not a pivot-joint support simulation; no contact, bolt preload, fatigue, buckling, plasticity or qualified print material.',
        'Peak stresses near ideal clamps are not used as strength acceptance metrics.']}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    return report
