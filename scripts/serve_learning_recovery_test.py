"""Local fault injection fixture, never the production server. Preserves each run."""
from pathlib import Path
import uuid
import uvicorn
from cadforge import studio_server as server, region_edit
from cadforge.workspace import PythonWorkspace
root=Path('artifacts/learning-recovery-browser')/uuid.uuid4().hex
root.mkdir(parents=True)
store=root/'learning.json'
store.write_text('{intentional isolated corruption')
server.DATA=root.resolve()
server.workspace=PythonWorkspace(server.DATA/'sessions',region_learning_path=store.resolve())
original=region_edit.deform_region
counts={'geometry_executions':0}
def counted(*args,**kwargs):
    counts['geometry_executions']+=1
    return original(*args,**kwargs)
region_edit.deform_region=counted
@server.app.get('/api/test/status')
def status():return counts|{'root':str(root.resolve())}
@server.app.post('/api/test/repair-store')
def repair():
    store.rename(root/'preserved-corrupt-store.json')
    return status()
uvicorn.run(server.app,host='127.0.0.1',port=2741)
