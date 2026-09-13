"""Isolated restart test service. Same explicit directory survives each process."""
import os,sys
from pathlib import Path
import uvicorn
from cadforge import studio_server as server
from cadforge.workspace import PythonWorkspace
root=Path(sys.argv[1]).resolve()
base=Path('artifacts/learning-restart-browser').resolve()
if not root.is_relative_to(base):raise ValueError('Restart fixture must use its own artifact directory')
server.DATA=root
server.workspace=PythonWorkspace(root/'sessions',region_learning_path=root/'learning.json')
@server.app.get('/api/test/process')
def process():return {'pid':os.getpid(),'root':str(root)}
# The production UI mounts at '/', so fixture routes must precede that mount.
server.app.router.routes.insert(0,server.app.router.routes.pop())
uvicorn.run(server.app,host='127.0.0.1',port=2741)
