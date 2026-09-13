import {chromium} from '../studio/node_modules/playwright/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
const out=path.resolve('artifacts/axial-browser');
const browser=await chromium.launch({channel:'chrome',headless:true,args:['--enable-webgl','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1600,height:1000},acceptDownloads:true});
const report={errors:[]};page.on('pageerror',e=>report.errors.push(String(e)));
try {
 await page.goto('http://127.0.0.1:2757',{waitUntil:'networkidle'});
 await page.locator('#file-input').setInputFiles(path.join(out,'rotated-public-plate.stl'));
 await page.waitForFunction(()=>document.getElementById('document-name').textContent==='rotated-public-plate.stl');
 await page.locator('#busy').waitFor({state:'hidden'});
 await page.locator('.object-row').first().click();
 await page.locator('#prompt').fill('Make this 1 cm wider keeping holes fixed');
 const event=page.waitForResponse(r=>r.url().endsWith('/edit'));
 await page.locator('#send').click();report.result=await(await event).json();
 await page.locator('#busy').waitFor({state:'hidden'});
 if(!report.result.preview?.accepted)throw Error('Preview rejected');
 await page.screenshot({path:path.join(out,'preview.png')});
 await page.locator('#apply').click();await page.locator('#busy').waitFor({state:'hidden'});
 let download=page.waitForEvent('download');await page.locator('#export').click();await(await download).saveAs(path.join(out,'edited.stl'));
 await page.locator('#undo').click();await page.locator('#busy').waitFor({state:'hidden'});
 download=page.waitForEvent('download');await page.locator('#export').click();await(await download).saveAs(path.join(out,'undone.stl'));
 if(report.errors.length)throw Error('Browser errors');
} catch(error) {report.error=String(error);process.exitCode=1;}
finally {await fs.writeFile(path.join(out,'browser-result.json'),JSON.stringify(report,null,2));await browser.close();console.log(JSON.stringify({error:report.error,accepted:report.result?.preview?.accepted,usage:report.result?.usage}));}
