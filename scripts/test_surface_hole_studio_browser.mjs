/** Real-browser development acceptance test. No mocked API, planner, geometry or selection. */
import {chromium} from '../studio/node_modules/playwright/index.mjs';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const output=path.join(root,'artifacts','surface-hole-studio-test');
await fs.mkdir(output,{recursive:true});
const fixture=path.join(root,'artifacts','region-public','angle_block.STL');
await fs.access(fixture);
const browser=await chromium.launch({channel:'chrome',headless:true,args:['--enable-webgl','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const context=await browser.newContext({viewport:{width:1600,height:1000},acceptDownloads:true,recordVideo:{dir:path.join(output,'video'),size:{width:1600,height:1000}}});
const page=await context.newPage();
const errors=[],consoleErrors=[],responses=[];
page.on('pageerror',error=>errors.push(String(error)));
page.on('console',message=>{if(message.type()==='error')consoleErrors.push({text:message.text(),location:message.location()});});
page.on('response',response=>{if(response.url().includes('/api/'))responses.push({url:new URL(response.url()).pathname,status:response.status()});});
const summary={fixture,declared_import_units:'in',units_note:'STL is unitless; inches are explicitly selected for this development demonstration, not inferred manufacturing metadata.',interaction:'Native file input; actual WebGL canvas clicks; ordinary-language prompt; visible Apply/Undo/Export controls',mocked:false};
async function download(name){const event=page.waitForEvent('download',{timeout:30000});await page.locator('#export').click();const item=await event;const target=path.join(output,name);await item.saveAs(target);return target;}
try{
 await page.goto('http://localhost:2720',{waitUntil:'networkidle'});
 await page.locator('#units').selectOption('in');
 await page.locator('#file-input').setInputFiles(fixture);
 await page.waitForFunction(()=>document.getElementById('document-name').textContent==='angle_block.STL',{timeout:30000});
 await page.locator('#busy').waitFor({state:'hidden'});
 await page.waitForFunction(()=>document.querySelectorAll('#objects button').length>0,{timeout:15000});
 await page.locator('canvas').waitFor({state:'visible'});
 await page.waitForTimeout(600);
 summary.webgl=await page.locator('canvas').evaluate(canvas=>!!(canvas.getContext('webgl2')||canvas.getContext('webgl')));
 assert.equal(summary.webgl,true,'Canvas must own a working WebGL context');
 await page.locator('#select-object').click();
 await page.screenshot({path:path.join(output,'01-imported.png')});
 await page.locator('#side-view').click();
 await page.waitForTimeout(200);
 const xy=await page.evaluate(()=>window.cadforge.projectPoint([17,9.804399935404458,-10.179222623507181]));
 await page.mouse.click(xy.x,xy.y);
 await page.locator('#selection-details').waitFor({state:'visible'});
 summary.selection=await page.evaluate(()=>window.cadforge.getSelection());
 assert.ok(Math.abs(summary.selection.normal[0]-1)<1e-8,'Actual clicked side face must supply +X normal');
 summary.selectionText=await page.locator('#selection-details').innerText();
 await download('baseline.stl');
 await page.locator('#prompt').fill('Drill a 4 mm diameter hole 3 mm deep here');
 const editResponse=page.waitForResponse(r=>/\/api\/sessions\/[^/]+\/edit$/.test(new URL(r.url()).pathname),{timeout:120000});
 await page.locator('#send').click();
 const response=await editResponse;
 assert.equal(response.status(),200,await response.text());
 summary.edit=await response.json();
 assert.ok(summary.edit.preview?.accepted,'Actual planner and geometry must accept this valid protected width increase');
 assert.equal(summary.edit.preview.command.op,'drill_surface_hole');
 await page.locator('#preview-banner').waitFor({state:'visible',timeout:30000});
 await page.locator('#busy').waitFor({state:'hidden'});
 await page.screenshot({path:path.join(output,'02-preview.png')});
 await download('uncommitted-preview-export.stl');
 await page.locator('#apply').click();
 await page.locator('#preview-banner').waitFor({state:'hidden',timeout:30000});
 await page.locator('#busy').waitFor({state:'hidden'});
 await download('committed.stl');
 await page.screenshot({path:path.join(output,'03-committed.png')});
 await page.locator('#undo').click();
 await page.locator('#busy').waitFor({state:'hidden',timeout:30000});
 await page.getByText('Restored the previous version.',{exact:true}).waitFor();
 await download('undone.stl');
 await page.screenshot({path:path.join(output,'04-undone.png')});
 await fs.writeFile(path.join(output,'edit-command.json'),JSON.stringify(summary.edit.preview.command));
 const verification=execFileSync(path.join(root,'.venv/bin/python'),['-c',`
import json,hashlib,trimesh,numpy as np
from pathlib import Path
p=Path(${JSON.stringify(output)})
meshes={n:trimesh.load(p/(n+'.stl'),force='mesh') for n in ['baseline','uncommitted-preview-export','committed','undone']}
b=meshes['baseline'];c=meshes['committed'];u=meshes['undone'];v=meshes['uncommitted-preview-export']
command=json.loads((p/'edit-command.json').read_text())
entry=np.array(command['entry']);radius=command['radius_mm'];depth=command['depth_mm']
assert np.allclose(c.bounds,b.bounds,atol=2e-5)
near=c.vertices[np.linalg.norm(c.vertices[:,1:]-entry[1:],axis=1)<=radius+1e-4]
assert len(near)>0
actual_depth=entry[0]-near[:,0].min()
assert abs(actual_depth-depth)<2e-5,(actual_depth,depth)
expected=32*radius**2*np.sin(2*np.pi/64)*depth
removed=b.volume-c.volume
assert abs(removed-expected)<.002,(removed,expected)
assert c.is_watertight and c.is_winding_consistent and c.volume>0
assert (p/'baseline.stl').read_bytes()==(p/'uncommitted-preview-export.stl').read_bytes()
assert (p/'baseline.stl').read_bytes()==(p/'undone.stl').read_bytes()
print(json.dumps({'requested_depth_mm':depth,'actual_depth_mm':actual_depth,'removed_volume_mm3':removed,'expected_volume_mm3':expected,'preview_did_not_commit':True,'undo_exact_export':True,'watertight':bool(c.is_watertight)}))

`],{encoding:'utf8'});
 summary.geometry=JSON.parse(verification);
 assert.deepEqual(errors,[],'No uncaught browser errors');
 assert.deepEqual(consoleErrors,[],'No browser console errors');
 summary.passed=true;
}catch(error){summary.passed=false;summary.failure=String(error.stack||error);await page.screenshot({path:path.join(output,'failure.png')});process.exitCode=1;}
finally{summary.errors=errors;summary.consoleErrors=consoleErrors;summary.responses=responses;const recording=page.video();await context.close();if(recording){summary.video=path.join(output,'browser-flow.webm');await fs.copyFile(await recording.path(),summary.video);}await browser.close();await fs.writeFile(path.join(output,'browser-result.json'),JSON.stringify(summary,null,2));console.log(JSON.stringify({passed:summary.passed,failure:summary.failure,geometry:summary.geometry,planner:summary.edit?.planner,errors,consoleErrors},null,2));}
