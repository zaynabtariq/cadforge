#!/usr/bin/env node
// Record the regular Chrome UI and archive the independent Browserbase provider video.
import { chromium } from 'playwright';
import { mkdir, writeFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.dirname(fileURLToPath(import.meta.url));
const origin = process.env.QUOTE_UI_URL || 'http://127.0.0.1:8766';
const quantity = 2, material = 'Black Resin';
const directory = path.join(root, 'artifacts', `quote-recording-${new Date().toISOString().replace(/[:.]/g, '-')}`);
await mkdir(directory, { recursive: true });
const health = await (await fetch(`${origin}/api/health`)).json();
if (health.browser !== 'browserbase') throw new Error('Start server.py with --browserbase before recording.');

const browser = await chromium.launch({ channel: 'chrome', headless: false, args: ['--window-size=1440,1100'] });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1,
  recordVideo: { dir: directory, size: { width: 1440, height: 1000 } } });
const page = await context.newPage();
const video = page.video();
const marks = [];
let quoteSession;
const mark = async (label) => {
  marks.push({ label, timestamp: new Date().toISOString(), elapsed_ms: Date.now() - started });
  console.log(label);
  await writeFile(path.join(directory, 'timing.json'), JSON.stringify(marks, null, 2));
};
const started = Date.now();
try {
  await page.goto(origin);
  await mark('Select the demo model');
  await page.waitForTimeout(1500);
  await page.locator('#demo').click();
  await page.waitForFunction(() => window.quoteUI?.state?.id);
  quoteSession = await page.evaluate(() => window.quoteUI.state.id);
  await mark('Set quantity to two');
  await page.locator('#quantity').fill(String(quantity));
  await page.locator('#quantity').press('Tab');
  await page.waitForTimeout(1500);
  await page.locator('#next-material').click();
  await mark('Choose Black Resin');
  await page.waitForFunction(value => Array.from(document.querySelector('#material').options).some(o => o.value === value), material);
  await page.locator('#material').selectOption(material);
  await page.waitForTimeout(1500);
  await page.locator('#next-review').click();
  await mark('Wait for the provider to verify the quote');
  await page.waitForFunction(() => {
    const ui = window.quoteUI;
    return ui?.state?.error || (ui?.current && !ui.state.busy && !ui.state.quote.baseline && ui.state.quote.shipping_status !== 'pending');
  }, null, { timeout: 300000 });
  const result = await page.evaluate(() => window.quoteUI);
  if (result.state.error) throw new Error(result.state.error);
  const quote = result.state.quote;
  if (quote.config.quantity !== quantity || quote.config.material !== material) throw new Error('Quote differs from scripted selections');
  await mark('Verified quote ready');
  await writeFile(path.join(directory, 'quote.json'), JSON.stringify(quote, null, 2));
  await page.screenshot({ path: path.join(directory, 'quote.png'), fullPage: true });
  await page.waitForTimeout(5000);
  await fetch(`${origin}/api/sessions/${quoteSession}`, { method: 'DELETE' });
  await context.close(); // Flush the UI recording before preparing the provider recording.
  await video.saveAs(path.join(directory, 'ui.webm'));
  await video.delete();
  const transcode = spawnSync('ffmpeg', ['-y', '-i', path.join(directory, 'ui.webm'), '-c:v', 'libx264',
    '-preset', 'fast', '-crf', '20', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', path.join(directory, 'ui.mp4')], { encoding: 'utf8' });
  if (transcode.status !== 0) console.log('UI WebM saved; MP4 conversion was unavailable.');
  await mark('UI recording saved; requesting the separate Browserbase recording');
  const deadline = Date.now() + 360000;
  let recording;
  while (Date.now() < deadline) {
    recording = await (await fetch(`${origin}/api/sessions/${quoteSession}/browser`)).json();
    if (recording.status === 'error') throw new Error(recording.message);
    if (recording.status === 'ready') break;
    await new Promise(resolve => setTimeout(resolve, 3000));
  }
  if (recording.status !== 'ready') throw new Error('Browserbase recording is still processing');
  for (const p of recording.pages) {
    const response = await fetch(`${origin}/api/sessions/${quoteSession}/recording/${p.page_id}.mp4`);
    if (!response.ok) throw new Error('Could not copy the provider recording');
    await writeFile(path.join(directory, `browserbase-${p.page_id}.mp4`), Buffer.from(await response.arrayBuffer()));
  }
  const manifest = { quote_session: quoteSession, browserbase_session: recording.session_id,
    browserbase_dashboard: recording.dashboard_url, directory, ui: transcode.status === 0 ? 'ui.mp4' : 'ui.webm',
    provider: recording.pages.map(p => `browserbase-${p.page_id}.mp4`),
    timing: 'timing.json', quote: 'quote.json' };
  await writeFile(path.join(directory, 'result.json'), JSON.stringify(manifest, null, 2));
  await mark('Both recordings saved separately');
  console.log(JSON.stringify(manifest, null, 2));
  // Leave a normal Chrome window showing the UI recording for review.
  const review = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const tab = await review.newPage();
  await tab.goto('file://' + path.join(directory, 'ui.mp4'));
  console.log('Review window is open. Close Chrome when finished.');
  await new Promise(resolve => browser.on('disconnected', resolve));
} catch (error) {
  await writeFile(path.join(directory, 'error.json'), JSON.stringify({ error: error.message, quote_session: quoteSession }, null, 2));
  await context.close().catch(() => {});
  if (quoteSession) await fetch(`${origin}/api/sessions/${quoteSession}`, { method: 'DELETE' }).catch(() => {});
  await browser.close();
  throw error;
}
