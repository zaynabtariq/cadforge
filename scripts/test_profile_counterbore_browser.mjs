import {chromium} from '../studio/node_modules/playwright/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
const root=process.cwd(),out=path.join(root,'artifacts/profile-counterbore-browser');
await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch({channel:'chrome',headless:true,args:['--enable-webgl','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const context=await browser.newContext({viewport:{width:1600,height:1000},acceptDownloads:true,recordVideo:{dir:path.join(out,'video'),size:{width:1600,height:1000}}});
const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(String(e)));let result={fixture_scope:'Unmodified public plate_holes.STL, existing central stepped bore'};
async function submit(text){await page.locator('#prompt').fill(text);const response=page.waitForResponse(r=>r.url().endsWith('/edit'));await page.locator('#send').click();return (await response).json();}
async function download(name){const event=page.waitForEvent('download');await page.locator('#export').click();await (await event).saveAs(path.join(out,name));}
try{
 await page.goto('http://127.0.0.1:2721',{waitUntil:'networkidle'});
 await page.locator('#file-input').setInputFiles(path.join(root,'artifacts/region-public/plate_holes.STL'));
 await page.waitForFunction(()=>document.getElementById('document-name').textContent==='plate_holes.STL');await page.locator('#busy').waitFor({state:'hidden'});
 await page.locator('#top-view').click();await page.waitForTimeout(300);
 const point=await page.evaluate(()=>window.cadforge.projectPoint([107.25,154.48074,12.7]));await page.mouse.click(point.x,point.y);
 await download('baseline.stl');
 result.edit=await submit('Counterbore this hole to 15 mm diameter and 2 mm deep');
 assert.equal(result.edit.preview?.accepted,true,JSON.stringify(result.edit));assert.equal(result.edit.preview.created_features[0].kind,'profile_counterbore');
 await page.locator('#busy').waitFor({state:'hidden'});await page.screenshot({path:path.join(out,'preview.png')});
 await page.locator('#apply').click();await page.locator('#busy').waitFor({state:'hidden'});await download('edited.stl');
 await page.locator('#undo').click();await page.locator('#busy').waitFor({state:'hidden'});await download('undone.stl');
 assert.deepEqual(await fs.readFile(path.join(out,'baseline.stl')),await fs.readFile(path.join(out,'undone.stl')));
 assert.deepEqual(errors,[]);result.passed=true;
}catch(e){result.failure=String(e.stack||e);process.exitCode=1;}
finally{result.errors=errors;const video=page.video();await context.close();if(video)await fs.copyFile(await video.path(),path.join(out,'browser-flow.webm'));await browser.close();await fs.writeFile(path.join(out,'result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify({passed:result.passed,failure:result.failure,errors}));}
