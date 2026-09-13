"""Installed-package review/export acceptance; run outside the source checkout."""
import asyncio,json
from pathlib import Path
from cadforge import mcpserver
from cadforge.handoff import verify_handoff
from cadforge.runtime_paths import artifact_directory

async def main():
    response=await mcpserver.create_server().call_tool('create_camera_glasses',{
        'parameters':{},'review_inputs':{'tool_access':[{
            'name':'declared_test_approach','origin':[0,0,200],'axis':[0,0,1],
            'radius_mm':3,'length_mm':20,'source':'Synthetic installation test approach, not product qualification'}]}})
    assert not response.is_error
    result=json.loads(response.content[0].text)
    manifest=Path(result['exports']['manufacturing_manifest'])
    integrity=verify_handoff(manifest);assert integrity['integrity_passed']
    data=json.loads(manifest.read_text());assert len(data['review_evidence'])==4
    contract=json.loads((manifest.parent/data['review_evidence']['prebuild_contract']).read_text())
    assert contract['tool_access'][0]['name']=='declared_test_approach'
    assert len(contract['required_parts'])==6
    geometry=json.loads(Path(result['exports']['geometry_screen']).read_text())
    assert geometry['geometry_passed'] and len(geometry['parts'])==6
    report={'installed_module':mcpserver.__file__,'manifest':str(manifest),'file_count':integrity['file_count'],
        'review_roles':list(data['review_evidence']),'geometry_passed':True,'production_ready':False,
        'scope':'Installed MCP/production boundary and export acceptance; synthetic tool witness, no physical qualification'}
    (artifact_directory()/'installed-review-result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))

if __name__=='__main__':asyncio.run(main())
