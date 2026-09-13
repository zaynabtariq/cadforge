"""Local import-and-edit workspace HTTP boundary. Generated plans are data only."""
from __future__ import annotations
from pathlib import Path
import json
import os
import threading
import uuid
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from .workspace import PythonWorkspace,MAX_BYTES
from .edit_planner import plan_edit

from .runtime_paths import artifact_directory
DATA=artifact_directory()/'studio'
workspace=PythonWorkspace(DATA/'sessions')
app=FastAPI(title='CADForge local workspace')
_edit_lock=threading.Lock()
_trace=None

def trace_edit(fn):
    global _trace
    if os.getenv('CADFORGE_STUDIO_WEAVE')=='1' and _trace is None:
        try:
            from .cloud import init_development
            _trace=init_development()
        except Exception:
            _trace=False
    if _trace:
        import weave
        return weave.op()(fn)
    return fn

@app.exception_handler(ValueError)
async def invalid_request(request,error):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=400,content={'detail':str(error)})

@app.post('/api/import')
async def import_model(file:UploadFile=File(...),units:str=Form('mm')):
    extension=Path(file.filename or '').suffix.lower()
    if extension not in ('.stl','.step','.stp','.cadforge'):raise ValueError('Choose an STL, STEP or CADForge project file')
    limit=100*1024*1024 if extension=='.cadforge' else MAX_BYTES
    content=await file.read(limit+1)
    if len(content)>limit:raise ValueError('File exceeds the import size limit')
    folder=DATA/'uploads'/uuid.uuid4().hex;folder.mkdir(parents=True)
    filename=Path(file.filename or 'model.stl').name
    path=folder/filename;path.write_bytes(content)
    return workspace.import_project(path) if extension=='.cadforge' else workspace.import_file(path,units)

@app.post('/api/sample')
def sample():
    import trimesh
    folder=DATA/'samples';folder.mkdir(parents=True,exist_ok=True)
    path=folder/'starter-block.stl'
    if not path.exists():trimesh.creation.box(extents=[40,24,12]).export(path)
    return workspace.import_file(path)

@app.get('/api/sessions/{session_id}')
def session_state(session_id:str):return workspace.state(session_id)

@app.get('/api/learning')
def learning_history():
    from .edit_learning import history
    return history(path=workspace.region_learning_path)

class EditRequest(BaseModel):
    request:str=Field(min_length=1,max_length=4000)
    selection:dict|None=None
    base_revision:int|None=Field(default=None,ge=0)

@app.post('/api/sessions/{session_id}/edit')
def edit(session_id:str,body:EditRequest):
    with _edit_lock:
        state=workspace.state(session_id)
        if body.base_revision is not None and body.base_revision!=state['revision']:
            raise ValueError('Workspace changed; refresh before requesting an edit')
        selection=body.selection or {}
        @trace_edit
        def plan_and_check(request:str,selection:dict,geometry_context:dict):
            from .sequence_planner import plan_sequence
            sequence=plan_sequence(workspace,session_id,request,selection,state['revision'])
            if sequence is not None:return sequence
            decision=plan_edit(request,selection,geometry_context)
            if decision.get('clarification'):return decision
            preview=workspace.preview(session_id,decision['command'],selection,expected_revision=state['revision'],dimension_rule=decision.get('dimension_rule'))
            return decision|{'preview':preview}
        # Public local user workspace only; no hidden benchmark inputs.
        result=plan_and_check(body.request,selection,state)
        if result is None:raise RuntimeError('Edit failed; see local trace')
        return result

class SequenceRequest(BaseModel):
    steps:list[dict]=Field(min_length=2,max_length=8)
    invariants:list[dict]=Field(default_factory=list,max_length=8)
    base_revision:int=Field(ge=0)

@app.post('/api/sessions/{session_id}/sequence')
def sequence(session_id:str,body:SequenceRequest):
    return workspace.preview_sequence(session_id,body.steps,expected_revision=body.base_revision,invariants=body.invariants)

class CommitRequest(BaseModel):preview_id:str
@app.post('/api/sessions/{session_id}/commit')
def commit(session_id:str,body:CommitRequest):return workspace.commit(session_id,body.preview_id)
@app.post('/api/sessions/{session_id}/undo')
def undo(session_id:str):return workspace.undo(session_id)
@app.post('/api/sessions/{session_id}/previews/{preview_id}/learning/retry')
def retry_learning(session_id:str,preview_id:str):
    return workspace.retry_learning(session_id,preview_id)
@app.get('/api/sessions/{session_id}/export')
def export(session_id:str):
    path=workspace.export_path(session_id)
    return FileResponse(path,media_type='model/stl',filename='cadforge-edited.stl')
@app.get('/api/sessions/{session_id}/project')
def export_project(session_id:str):
    path=workspace.export_project(session_id)
    return FileResponse(path,media_type='application/json',filename='cadforge-project.cadforge')
@app.get('/api/file')
def asset(path:str):
    target=Path(path).resolve()
    if not target.is_relative_to(DATA.resolve()) or target.suffix.lower()!='.stl' or not target.is_file():
        raise HTTPException(404,'Workspace mesh not found')
    return FileResponse(target,media_type='model/stl')

# API routes stay ahead of the static mount; missing API paths remain 404.
from fastapi.staticfiles import StaticFiles
_static=Path(__file__).with_name('static')
if not (_static/'index.html').is_file():
    _static=Path(__file__).resolve().parents[2]/'studio'/'dist'
if (_static/'index.html').is_file():
    app.mount('/',StaticFiles(directory=str(_static),html=True),name='studio-ui')
else:
    @app.get('/')
    def missing_ui():
        from fastapi.responses import HTMLResponse
        return HTMLResponse('CADForge UI is not built. From the source checkout run npm --prefix studio run build, or install a bundled wheel.',status_code=503)


def main():
    import argparse
    import uvicorn
    parser=argparse.ArgumentParser(description='Run the local CADForge editor and API')
    parser.add_argument('--port',type=int,default=2721)
    args=parser.parse_args()
    if not 1<=args.port<=65535:parser.error('port must be between 1 and 65535')
    uvicorn.run(app,host='127.0.0.1',port=args.port)

if __name__=='__main__':main()
