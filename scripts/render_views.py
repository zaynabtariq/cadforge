"""Measured STL renders; no generated imagery or visual pass claims."""
import argparse
from pathlib import Path
import numpy as np
import trimesh
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

p=argparse.ArgumentParser();p.add_argument('stl',type=Path);p.add_argument('--output',type=Path,default=Path('artifacts/views.png'));args=p.parse_args()
mesh=trimesh.load(args.stl,force='mesh')
fig=plt.figure(figsize=(16,9),facecolor='#111b2c')
for index,(elevation,azimuth,label) in enumerate([(25,-60,'Assembly'),(0,0,'Side'),(90,-90,'Front'),(25,120,'Rear')]):
 ax=fig.add_subplot(2,2,index+1,projection='3d',facecolor='#111b2c')
 poly=Poly3DCollection(mesh.triangles,facecolor='#6dcce2',edgecolor='#44728a',linewidth=.1,alpha=.94)
 ax.add_collection3d(poly)
 lo,hi=mesh.bounds;center=(lo+hi)/2;radius=max(hi-lo)/2*1.1
 for axis,mid in zip('xyz',center): getattr(ax,'set_'+axis+'lim')(mid-radius,mid+radius)
 ax.set_box_aspect((1,1,1));ax.view_init(elev=elevation,azim=azimuth);ax.set_axis_off();ax.set_title(label,color='white')
fig.suptitle('CADForge · Camera + Raspberry Pi glasses | geometric prototype',color='white',fontsize=18)
args.output.parent.mkdir(parents=True,exist_ok=True);fig.savefig(args.output,dpi=150,bbox_inches='tight');print(args.output)
