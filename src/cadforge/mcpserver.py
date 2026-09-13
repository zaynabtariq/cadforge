"""CADForge engineering tools over MCP, optionally traced explicitly with Weave."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import uuid
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .runtime_paths import artifact_directory
from .review_json import ReviewInput
from .schema import DesignSpec
ARTIFACTS=artifact_directory()
ReviewInput.model_rebuild()

def create_server(tracing=False):
    decorate=lambda fn:fn
    if tracing:
        from .cloud import init_development
        init_development()
        import weave
        decorate=lambda fn:weave.op()(fn)
    server=MCPServer('CADForge continual engineering',instructions='Use measured engineering tools. Production readiness requires blocked qualification gates to be resolved with physical evidence. Learned factors are ideal CAD measurements, not manufacturing calibration. Never send private benchmark cases to these development tools.')

    def studio(method,path,**kwargs):
        # All writes go through one local workspace owner, including MCP clients.
        # A second in-process workspace here would bypass the HTTP owner's lock.
        import httpx
        try:
            response=httpx.request(method,'http://127.0.0.1:2721/api'+path,timeout=90,**kwargs)
        except httpx.ConnectError as error:
            raise ToolError('Start the local CADForge studio server before using workspace tools') from error
        if response.is_error:
            raise ToolError(response.json().get('detail','Workspace request failed'))
        return response.json()

    @server.tool()
    @decorate
    def import_cad_workspace(path:str,units:str='mm')->dict:
        """Import a user-selected local STL/STEP into the same versioned workspace as the UI."""
        source=Path(path)
        if source.suffix.lower() not in ('.stl','.step','.stp') or not source.is_file():
            raise ToolError('Select an existing STL or STEP file')
        if source.stat().st_size>50*1024*1024:
            raise ToolError('Import exceeds 50 MiB')
        with source.open('rb') as stream:
            return studio('POST','/import',files={'file':(source.name,stream)},data={'units':units})

    @server.tool()
    def get_cad_workspace(session_id:str)->dict:
        """Read current parts, version and edit history."""
        if not session_id.isalnum():raise ToolError('Invalid session identifier')
        return studio('GET','/sessions/'+session_id)

    @server.tool()
    @decorate
    def preview_cad_edit(session_id:str,request:str,selection:dict,base_revision:int)->dict:
        """Plan a preview for the revision returned by get_cad_workspace; selection includes part_id and optional region/point."""
        if not session_id.isalnum():raise ToolError('Invalid session identifier')
        return studio('POST','/sessions/'+session_id+'/edit',json={'request':request,'selection':selection,'base_revision':base_revision})

    @server.tool()
    @decorate
    def apply_cad_preview(session_id:str,preview_id:str)->dict:
        """Commit a reviewed accepted preview; stale or failed previews are rejected."""
        if not session_id.isalnum():raise ToolError('Invalid session identifier')
        return studio('POST','/sessions/'+session_id+'/commit',json={'preview_id':preview_id})

    @server.tool()
    @decorate
    def undo_cad_edit(session_id:str)->dict:
        """Restore the prior committed version while preserving audit history."""
        if not session_id.isalnum():raise ToolError('Invalid session identifier')
        return studio('POST','/sessions/'+session_id+'/undo',json={})

    @server.tool()
    @decorate
    def measure_fastener_fit(fastener_diameter:float,radial_clearance:float,bore_diameter:float,boss_outer_diameter:float,min_wall:float=1.5,family_code:int=0)->dict:
        """Build an ideal CAD coupon and measure screw insertion and radial boss wall."""
        from dataclasses import asdict
        from .fit_experiments import measure_coupon
        return asdict(measure_coupon(dict(fastener_diameter=fastener_diameter,radial_clearance=radial_clearance,bore_diameter=bore_diameter,boss_outer_diameter=boss_outer_diameter,min_wall=min_wall,family_code=float(family_code))))

    @server.tool()
    @decorate
    def learn_engineering_factors()->dict:
        """Run bounded development discovery or reuse and monitor persisted validated commands."""
        from .evolve import evolve
        return evolve(output_dir=ARTIFACTS/'continual',cloud=False)

    @server.tool()
    @decorate
    def apply_learned_fastener(fastener_diameter:float,radial_clearance:float,min_wall:float)->dict:
        """Compose previously promoted bore and bearing-wall commands in supported ranges."""
        from .continual import ContinualLearning
        from .evolve import DEFAULT_DB,context
        store=ContinualLearning(DEFAULT_DB)
        try:
            return store.apply('supported_fastener',dict(fastener_diameter=fastener_diameter,radial_clearance=radial_clearance,min_wall=min_wall,bore_diameter=fastener_diameter,boss_outer_diameter=fastener_diameter+.2),context=context())
        finally:store.close()

    @server.tool()
    @decorate
    def create_camera_glasses(parameters:dict[str,float],review_inputs:dict|None=None)->dict:
        """Build an editable Pi Zero 2 W / Camera Module 3 prototype and return independent engineering gates."""
        from .product import run_production
        from .schema import DesignSpec
        if review_inputs is None:
            review=None
        else:
            review=ReviewInput.model_validate(review_inputs).contracts()
        folder=ARTIFACTS/'production'/uuid.uuid4().hex[:12]
        if review is None:return run_production(DesignSpec(family='glasses',parameters=parameters),folder)
        return run_production(DesignSpec(family='glasses',parameters=parameters),folder,review_inputs=review)

    @server.tool()
    @decorate
    def review_camera_glasses_handoff(manifest_path:str,expected_specification:dict,review_inputs:dict|None=None)->dict:
        """Review named STEP parts against an explicit complete specification; never execute packaged Python. Development packages only."""
        from .handoff_review import review_handoff
        if review_inputs is None:
            review=None
        else:
            review=ReviewInput.model_validate(review_inputs).contracts()
        folder=ARTIFACTS/'engineering-reviews'/uuid.uuid4().hex
        result=review_handoff(manifest_path,DesignSpec.model_validate(expected_specification),folder,review_inputs=review)
        return {**result,'review_directory':str(folder.resolve())}

    @server.resource('cadforge://learning/status')
    def learning_status()->str:
        from .continual import ContinualLearning
        from .evolve import DEFAULT_DB
        store=ContinualLearning(DEFAULT_DB)
        try:return json.dumps(store.audit())
        finally:store.close()

    @server.tool()
    @decorate
    def widen_robot_link(parameters:dict[str,float],new_width:float)->dict:
        """Widen a parameterized two-pivot link, preserving measured pivots and rolling back invalid edits."""
        from dataclasses import asdict
        from .robotics import RobotLinkSpec,build_link,widen_link,export_link
        folder=ARTIFACTS/'robotics'/uuid.uuid4().hex[:12]
        original=build_link(RobotLinkSpec(**parameters))
        before_exports=export_link(original,folder/'before')
        change=widen_link(original,new_width,output_dir=folder/'changes')
        exports=export_link(change.active_link,folder/'active')
        return {'accepted':change.accepted,'checks':change.checks,'error':change.error,
                'before':asdict(change.before),'after':asdict(change.after) if change.after else None,
                'active_version':change.active_link.version_id,'previous_version':change.previous_version,
                'exports':exports,'before_exports':before_exports,'production_ready':False}
    return server

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--weave',action='store_true');args=p.parse_args()
    create_server(args.weave).run(transport='stdio')
