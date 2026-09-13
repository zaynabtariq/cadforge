import {chromium} from '../studio/node_modules/playwright/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';

const AMOUNT_MM = Number(process.env.LEARNING_MOVE_MM || '12');
const root = path.resolve('.');
const output = path.join(root, 'artifacts', 'learning-loop-video');
await fs.mkdir(output, { recursive: true });

const browser = await chromium.launch({
  channel: 'chrome',
  headless: true,
  args: ['--enable-webgl', '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
});
const context = await browser.newContext({
  viewport: { width: 1600, height: 1000 },
  acceptDownloads: true,
  recordVideo: { dir: path.join(output, 'raw'), size: { width: 1600, height: 1000 } },
});
const page = await context.newPage();

const records = [];
let failure = null;
let videoPath = null;

try {
  await page.goto('http://127.0.0.1:2721', { waitUntil: 'networkidle' });
  await page.locator('#file-input').setInputFiles(path.join(root, 'artifacts', 'studio-test', '20mm-xyz-cube.stl'));
  await page.waitForFunction(() => document.getElementById('document-name').textContent === '20mm-xyz-cube.stl', { timeout: 30000 });
  await page.locator('#busy').waitFor({ state: 'hidden' });

  const canvas = page.locator('canvas');
  await canvas.waitFor({ state: 'visible' });
  const bounds = await canvas.boundingBox();

  for (let index = 0; index < 1; index++) {
    await page.locator('#select-region').click();
    const r = {
      x0: bounds.x + bounds.width * 0.35,
      y0: bounds.y + bounds.height * 0.35,
      x1: bounds.x + bounds.width * 0.65,
      y1: bounds.y + bounds.height * 0.65,
    };
    await page.mouse.move(r.x0, r.y0);
    await page.mouse.down();
    await page.mouse.move(r.x1, r.y1, { steps: 20 });
    await page.mouse.up();
    await page.waitForTimeout(400);

    const hasRegion = await page.locator('#selection-details').isVisible();
    if (!hasRegion) throw new Error('Section selection did not produce visible selection details');
    const selection = await page.evaluate(() => window.cadforge.getSelection());

    await page.locator('#prompt').fill(`Move this ${AMOUNT_MM} mm to the right`);
    const responseEvent = page.waitForResponse(
      (r) => /\/api\/sessions\/[^/]+\/edit$/.test(new URL(r.url()).pathname),
      { timeout: 120000 }
    );
    await page.locator('#send').click();
    const response = await responseEvent;
    const result = await response.json();

    records.push({
      step: index + 1,
      status: response.status(),
      learning: result.preview?.learning?.status,
      attempts: result.preview?.learning?.attempts,
      accepted: result.preview?.accepted,
      command: result.command?.op,
      axis: result.command?.axis,
      amount_mm: result.command?.amount_mm,
      selection,
    });

    await page.locator('#busy').waitFor({ state: 'hidden', timeout: 120000 });
    await page.waitForTimeout(700);

    if (!result.preview?.accepted) {
      throw new Error('Preview rejected for loop test: ' + JSON.stringify(result.preview?.error || result.error));
    }

    await page.locator('#apply').click();
    await page.locator('#busy').waitFor({ state: 'hidden', timeout: 120000 });
    await page.waitForTimeout(400);
    await page.screenshot({ path: path.join(output, `step-${index + 1}-post.png`) });
  }

  await page.screenshot({ path: path.join(output, 'final.png') });
  console.log(JSON.stringify({ learningLoop: records }, null, 2));
} catch (error) {
  failure = String(error.stack || error);
  await page.screenshot({ path: path.join(output, 'failure.png') });
  console.log(JSON.stringify({ failure, learningLoop: records }, null, 2));
  process.exitCode = 1;
} finally {
  const video = page.video();
  await context.close();
  if (video) {
    videoPath = path.join(output, 'learning-loop.webm');
    await fs.copyFile(await video.path(), videoPath);
  }
  await browser.close();
  const summary = { output, failure, video: videoPath, records };
  await fs.writeFile(path.join(output, 'result.json'), JSON.stringify(summary, null, 2));
}
