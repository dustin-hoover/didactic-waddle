// Drives the DockOS Crew PWA in headless Chromium against a running dispatch API (doc 23).
// node pwa_check.mjs <base> <crew> <day> <install_wo> <mac> <offline_wo>  -> JSON on stdout
import pkg from '/opt/node22/lib/node_modules/playwright/index.js';
const { chromium } = pkg;
const [base, crew, day, woInstall, mac, woOffline] = process.argv.slice(2);
const out = { errors: [] };
const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
const ctx = await browser.newContext({ viewport: { width: 400, height: 860 } });   // phone width
const page = await ctx.newPage();
page.on('pageerror', e => out.errors.push('pageerror: ' + e.message));
page.on('console', m => { if (m.type() === 'error' && !/fonts\.g|ERR_CERT_AUTHORITY_INVALID/.test(m.text()))  /* sandbox proxy CA vs external fonts */ out.errors.push('console: ' + m.text()); });
const act = async () => { await page.click('#act'); await page.waitForTimeout(700); };

await page.goto(`${base}/crew/?crew=${crew}&day=${day}`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.stop', { timeout: 20000 });
out.stops = await page.$$eval('.stop', els => els.map(e => ({ wo: +e.dataset.wo, text: e.innerText.replace(/\s+/g, ' ') })));
out.header = await page.$eval('#crew', e => e.textContent);
out.bodyScrollsSideways = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);

// install at the dock: tie up -> start -> readings -> complete -> leave
await page.click(`.stop[data-wo="${woInstall}"]`);
out.firstButton = await page.$eval('#act', e => e.textContent);
await act();                                               // tied up at the dock
out.secondButton = await page.$eval('#act', e => e.textContent);
await act();                                               // start work
out.completeDisabledBefore = await page.$eval('#act', e => e.disabled);
await page.fill('#cap-device_mac', mac);
await page.fill('#cap-speed_down_mbps', '612');
await page.fill('#cap-speed_up_mbps', '188');
await page.fill('#cap-rssi_dbm', '-61');
out.completeDisabledAfter = await page.$eval('#act', e => e.disabled);
await page.click('#act');                                  // complete job
try {
  await page.waitForFunction(() => !document.getElementById('toast').hidden && /bill|closed/i.test(document.getElementById('toast').textContent), null, { timeout: 20000 });
} catch (e) {
  out.debug = await page.evaluate(() => ({ toast: document.getElementById('toast').textContent, chips: document.getElementById('chips').textContent,
    outbox: localStorage.getItem('bdn.outbox'), act: (document.getElementById('act') || {}).textContent }));
  console.log(JSON.stringify(out)); await browser.close(); process.exit(0);
}
out.toast = await page.$eval('#toast', e => e.textContent);
out.leaveButton = await page.$eval('#act', e => e.textContent);
await act();                                               // leaving the dock -> back to the run
await page.waitForFunction(() => /All synced/.test(document.getElementById('chips').textContent), null, { timeout: 20000 });

// no signal on the lake: queue an action offline, then reconnect
await ctx.setOffline(true);
await page.click(`.stop[data-wo="${woOffline}"]`);
await act();                                               // tied up (queued)
out.chipsOffline = await page.$eval('#chips', e => e.textContent);
await ctx.setOffline(false);
await page.waitForFunction(() => /All synced/.test(document.getElementById('chips').textContent), null, { timeout: 30000 });
out.chipsAfter = await page.$eval('#chips', e => e.textContent);
await page.screenshot({ path: process.env.SHOT || '/dev/null' });
console.log(JSON.stringify(out));
await browser.close();
