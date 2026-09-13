/** Actual UI region discovery/transfer/reuse recording. Never resets persisted evidence. */
import {chromium} from '../studio/node_modules/playwright/index.mjs';
import fs from 'node:fs/promises';import path from 'node:path';import {fileURLToPath} from 'node:url';import {execFileSync,spawn} from 'node:child_process';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const output=process.env.CADFORGE_LEARNING_VIDEO_DIR?path.resolve(process.env.CADFORGE_LEARNING_VIDEO_DIR):path.join(root,'artifacts','learning-restart-browser');await fs.mkdir(output,{recursive:true});
const runRoot=path.join(output,String(Date.now()));await fs.mkdir(runRoot);
const log=await fs.open(path.join(runRoot,'server.log'),'a');
let backend=null;const restartEvidence=[];
async function startBackend(){
 backend=spawn(path.join(root,'.venv/bin/python'),[path.join(root,'scripts/serve_learning_restart_test.py'),runRoot],{cwd:root,env:{...process.env,CADFORGE_STUDIO_WEAVE:'1'},stdio:['ignore',log.fd,log.fd]});
 for(let n=0;n<100;n++){
  if(backend.exitCode!==null)throw Error('Fixture backend exited');
  try{const r=await fetch('http://127.0.0.1:2741/api/test/process');if(r.ok){const data=await r.json();if(data.pid!==backend.pid)throw Error('Unexpected service on fixture port');return data;}}catch(e){if(e.message.includes('Unexpected'))throw e;}
  await new Promise(resolve=>setTimeout(resolve,100));
 }
 throw Error('Backend did not become ready');
}
async function stopBackend(){if(backend&&backend.exitCode===null){const done=new Promise(resolve=>backend.once('exit',resolve));backend.kill('SIGTERM');await done;}}
const initialProcess=await startBackend();
const selectionOnly=process.argv.includes('--selection-only');
const steps=[{model:'plate_holes.STL',axis:2,view:'front-view',amount:12},{model:'round.stl',axis:1,view:'side-view',amount:1},{model:'round.stl',axis:1,view:'side-view',amount:1,reuse:true}];
const browser=await chromium.launch({channel:'chrome',headless:true,args:['--enable-webgl','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const context=await browser.newContext({viewport:{width:1600,height:1000},acceptDownloads:true,recordVideo:{dir:path.join(output,'raw'),size:{width:1600,height:1000}}});
const page=await context.newPage();const records=[],errors=[];page.on('pageerror',e=>errors.push(String(e)));
let failure=null;let videoPath=null;
try{
 await page.goto('http://localhost:2740',{waitUntil:'networkidle'});
 // Actual user-visible history opening records that prior knowledge is not erased.
 await page.locator('#history-toggle').click();await page.waitForTimeout(700);
 await page.screenshot({path:path.join(output,'00-existing-history.png')});
 await page.locator('#history-toggle').click();
 for(let index=0;index<(selectionOnly?2:steps.length);index++){
  if(index===2){
   const before=await fs.readFile(path.join(runRoot,'learning.json'));
   await stopBackend();const restarted=await startBackend();
   const after=await fs.readFile(path.join(runRoot,'learning.json'));
   if(initialProcess.pid===restarted.pid||!before.equals(after))throw Error('Restart identity or store preservation failed');
   restartEvidence.push({before_pid:initialProcess.pid,after_pid:restarted.pid,store_unchanged:true,store_bytes:before.length});
  }
  const step=steps[index];const fixture=path.join(root,'artifacts','region-public',step.model);
  const geometry=JSON.parse(execFileSync(path.join(root,'.venv/bin/python'),['-c',`import trimesh,json,numpy as np
m=trimesh.load(${JSON.stringify(fixture)},force='mesh');a=${step.axis};limit=m.bounds[0,a]+m.extents[a]*.25
v=m.vertices[m.vertices[:,a]>=limit-1e-6]
print(json.dumps({'points':v.tolist(),'target_min':v.min(axis=0).tolist(),'target_max':v.max(axis=0).tolist()}))`],{encoding:'utf8'}));
  if(step.reuse){await page.locator('#undo').click();await page.locator('#busy').waitFor({state:'hidden'});await page.waitForTimeout(600);}else await page.locator('#file-input').setInputFiles(fixture);
  await page.waitForFunction(name=>document.getElementById('document-name').textContent===name,step.model);
  await page.locator('#busy').waitFor({state:'hidden'});await page.waitForTimeout(250);
  await page.locator('#select-region').click();await page.locator('#'+step.view).click();await page.waitForTimeout(700);
  const screen=await page.evaluate(points=>points.map(p=>window.cadforge.projectPoint(p)),geometry.points);
  const xs=screen.map(p=>p.x),ys=screen.map(p=>p.y);
  const rectangle={x0:Math.min(...xs)-.1,y0:Math.min(...ys)-.1,x1:Math.max(...xs)+.1,y1:Math.max(...ys)+.1};
  await page.mouse.move(rectangle.x0,rectangle.y0);await page.mouse.down();await page.mouse.move(rectangle.x1,rectangle.y1,{steps:24});await page.mouse.up();await page.waitForTimeout(500);
  const selection=await page.evaluate(()=>window.cadforge.getSelection()); // Read-only audit of actual mouse selection.
  if(!selection?.region)throw Error('Actual marquee did not create region selection');
  const record={step:index+1,model:step.model,request:`Move this ${step.amount} mm to the right`,rectangle,selection,target:{min:geometry.target_min,max:geometry.target_max}};records.push(record);
  await page.screenshot({path:path.join(output,`${index+1}-selected.png`)});
  if(selectionOnly)continue;
  await page.locator('#iso-view').click();await page.waitForTimeout(700);
  await page.locator('#prompt').fill(record.request);await page.waitForTimeout(650);
  const responseEvent=page.waitForResponse(r=>/\/api\/sessions\/[^/]+\/edit$/.test(new URL(r.url()).pathname),{timeout:120000});
  await page.locator('#send').click();const response=await responseEvent;record.response=await response.json();record.http_status=response.status();
  await page.locator('#busy').waitFor({state:'hidden',timeout:120000});await page.waitForTimeout(1400);
  await page.screenshot({path:path.join(output,`${index+1}-actual-result.png`)});
  if(index===0&&record.response.preview?.learning?.status!=='candidate')throw Error('Expected fresh discovery candidate');
  if(index===1&&record.response.preview?.learning?.status!=='promoted')throw Error('Expected transfer promotion');
  if(index===2&&(record.response.preview?.learning?.status!=='reused'||record.response.preview?.learning?.attempts!==1))throw Error('Restart did not retain one-attempt reuse');
  // Every actual outcome, including a failed attempt, remains in the saved log/store.
  if(record.response.preview?.accepted){
   await page.locator('#apply').click();await page.locator('#busy').waitFor({state:'hidden'});
   const event=page.waitForEvent('download');await page.locator('#export').click();const file=await event;record.export=path.join(output,`${index+1}-edited.stl`);await file.saveAs(record.export);
  }else{throw Error('Actual region preview failed: '+JSON.stringify(record.response));}
  await page.waitForTimeout(600);
 }
 if(!selectionOnly){await page.locator('#history-toggle').click();await page.waitForTimeout(1500);await page.screenshot({path:path.join(output,'99-persisted-history.png')});}
}catch(error){failure=String(error.stack||error);await page.screenshot({path:path.join(output,'failure.png')});process.exitCode=1;}
finally{const video=page.video();await context.close();if(video){videoPath=path.join(output,selectionOnly?'selection-diagnostic.webm':'actual-learning-flow.webm');await fs.copyFile(await video.path(),videoPath);}await browser.close();await stopBackend();await log.close();const result={runRoot,restartEvidence,selectionOnly,records,errors,failure,video:videoPath,scope:'Actual public STL UI discovery and promotion, actual backend process shutdown and restart with unchanged isolated learning bytes, then real UI Undo and one-attempt reuse. No production store reset, mocked geometry, injected selection or hidden data.'};await fs.writeFile(path.join(output,selectionOnly?'selection-diagnostic.json':'actual-learning-result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify({failure,errors,records:records.map(r=>({step:r.step,model:r.model,selection:r.selection.region,target:r.target,accepted:r.response?.preview?.accepted,learning:r.response?.preview?.learning}))},null,2));}
