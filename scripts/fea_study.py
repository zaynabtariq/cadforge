"""Run real solver verification, then a nominal robot-link width comparison."""
from pathlib import Path
import json
from cadforge.geometry import box
from cadforge.fea import NominalLoad,solve_cantilever
from cadforge.robotics import RobotLinkSpec,build_link
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/fea'
load=NominalLoad(210000,.3,-10,'Synthetic 10 N verification/comparison force; E=210000 MPa, nu=.3 textbook isotropic steel-like fixture, not a selected product material.')
fixture=[]
for size in (4,2.5):
 r=solve_cantilever(box(100,10,5),OUT/f'beam-{size}',load,size)
 exact=abs(load.force_z_n)*100**3/(3*load.youngs_modulus_mpa*(10*5**3/12))
 r['euler_bernoulli_tip_mm']=exact;r['relative_displacement_error']=abs(abs(r['mean_tip_displacement_z_mm'])-exact)/exact
 fixture.append(r)
if fixture[-1]['relative_displacement_error']>.05:raise RuntimeError('Beam verification failed 5% analytic agreement criterion; robot comparison not run')
links=[]
for width in (20,28):
 for mesh in (4,2.5):
  r=solve_cantilever(build_link(RobotLinkSpec(width=width)).shape,OUT/f'link-{width}-{mesh}',load,mesh)
  r['width_mm']=width;links.append(r)
report={'verification':fixture,'robot_link_nominal_comparison':links,'engineering_ready':False,
 'verification_passed':True,'criterion':'Fine beam mesh within5% Euler-Bernoulli displacement before robot study.',
 'note':'A width change under synthetic end-clamp loading is not actual robot-joint strength qualification.'}
(OUT/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
