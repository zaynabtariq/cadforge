"""Exercise worker deadlines on public CAD; not a hidden evaluation."""
from dataclasses import asdict
import json,os,sys
from pathlib import Path
from cadforge.evaluation_process import run_worker
root=Path(__file__).resolve().parents[1]
code="""
import json,sys,trimesh
from cadforge.profile_counterbore import counterbore
p=json.load(sys.stdin)
m=trimesh.load(p['source'],force='mesh')
changed,checks,feature=counterbore(m,7.5,2,[101.5999984741211,154.48073817441445,12.699999809265137])
print(json.dumps({'accepted':all(c['passed'] for c in checks),'checks':len(checks),'volume_mm3':changed.volume}))
"""
request={'source':str(root/'artifacts/region-public/plate_holes.STL')}
results={}
for label,deadline in [('completed',10),('preempted',.01)]:
    result=run_worker([sys.executable,'-c',code],request,timeout_seconds=deadline,cwd=root,env={'PATH':os.environ['PATH']})
    results[label]=asdict(result)
assert results['completed']['status']=='completed' and results['completed']['report']['accepted']
assert results['preempted']['status']=='timeout' and results['preempted']['report'] is None
out=root/'artifacts/evaluation-worker';out.mkdir(parents=True,exist_ok=True)
(out/'public-cad-smoke.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results))
