/* Real-browser check: renders a clip grid and measures the action row.
 *
 * jsdom cannot lay CSS out, so the Home option wiring and the media behaviour are
 * checked there (scripts/ui_check.mjs) but the clip-card Download/Edit/More row
 * can only be proved in a layout engine. This runs headless Chromium against the
 * real stylesheet and asserts, at four widths, that all three controls are inside
 * the card, on one visual row when they fit, the intended grid when they do not,
 * and never overlapping.
 *
 *   node scripts/browser_check.mjs [--chrome /path/to/chrome] [--shots out/dir]
 *
 * Skips (exit 0 with a SKIP line) when no Chromium binary is available, so it is
 * harmless on machines without one. Needs puppeteer-core: `npm install puppeteer-core`.
 */
import { readFileSync, existsSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const flag = name => {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : null;
};
const shotDir = flag('--shots');

const require = createRequire(import.meta.url);
const NODE_PATH_DIRS = (process.env.NODE_PATH || '').split(':').filter(Boolean)
  .concat(['/tmp/browser/node_modules', '/tmp/jsdomtest/node_modules']);
let puppeteer = null;
for (const dir of [null, ...NODE_PATH_DIRS]) {
  try {
    puppeteer = dir ? require(require.resolve('puppeteer-core', { paths: [dir] })) : require('puppeteer-core');
    break;
  } catch (_) { /* keep looking */ }
}
if (!puppeteer) {
  console.log('SKIP puppeteer-core is not installed (npm install puppeteer-core)');
  process.exit(0);
}

const candidates = [
  flag('--chrome'),
  process.env.CHROME_PATH,
  '/tmp/chromium',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser',
  '/usr/bin/google-chrome'
].filter(Boolean);
const chrome = candidates.find(p => existsSync(p));
if (!chrome) {
  console.log('SKIP no Chromium binary found (pass --chrome /path/to/chrome)');
  process.exit(0);
}

const css = readFileSync(`${repo}/marrow/web/app.css`, 'utf8');
const failures = [];
const check = (name, ok, detail = '') => {
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${name}${detail ? ' - ' + detail : ''}`);
  if (!ok) failures.push(name);
};

const cardHtml = `
<article class="clip" data-rank="1">
  <div class="vid"><div class="score good" style="--v:88"><span>88</span></div>
    <span class="dur">0:42</span>
    <button class="expand" aria-label="Watch fullscreen">exp</button></div>
  <div class="cbody">
    <h3 dir="auto">A long clip title that wraps onto a second line to stress the card</h3>
    <div class="cmeta"><span>#podcast #clips #shorts</span></div>
    <div class="cactions">
      <button class="btn primary sm" data-act="download-clip">Download</button>
      <button class="btn sm" data-act="edit-clip">Edit</button>
      <details class="menu"><summary class="btn sm" aria-label="More actions">•••</summary>
        <div class="pop">
          <button type="button">Export…</button><button type="button">Subtitles</button>
          <button type="button">Copy title</button><button type="button">Delete clip</button>
        </div></details>
    </div>
  </div>
</article>`;

/* Markup is inlined rather than injected by a script: setContent() does not
   re-run inline scripts reliably on the second call, and a fresh page per width
   keeps every measurement honest. */
const pageHtml = `<!doctype html><html><head><meta charset="utf-8"><style>
  ${css}
  /* the checks only need geometry, not the app shell */
  body { margin: 0; padding: 20px; background: var(--bg); }
  #grid { display: grid; gap: 16px; }
</style></head><body><div id="grid" class="clips">${cardHtml.repeat(3)}</div></body></html>`;

// A sandbox Chromium built for a newer glibc needs its own NSS libs on the
// loader path; harmless elsewhere.
if (chrome === '/tmp/chromium' && existsSync('/tmp/al2023/lib')) {
  process.env.LD_LIBRARY_PATH = ['/tmp/al2023/lib', process.env.LD_LIBRARY_PATH || '']
    .filter(Boolean).join(':');
}

const browser = await puppeteer.launch({
  executablePath: chrome,
  headless: 'shell',
  args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu', '--hide-scrollbars',
         '--force-color-profile=srgb']
});
try {
  if (shotDir) mkdirSync(shotDir, { recursive: true });
  // 'row' = Download/Edit/More side by side; 'stacked' = Download on its own row
  // with Edit + More aligned underneath (the <=560px layout).
  for (const [w, label, mode] of [[1280, 'desktop', 'row'], [900, 'laptop', 'row'],
                                  [600, 'small-laptop', 'row'], [560, 'narrow', 'stacked'],
                                  [390, 'phone', 'stacked']]) {
    const page = await browser.newPage();          // a fresh page per width
    try {
    await page.setViewport({ width: w, height: 900, deviceScaleFactor: 1 });
    await page.setContent(pageHtml, { waitUntil: 'load' });
    await page.waitForSelector('.clip .cactions .menu > summary', { timeout: 5000 });
    const cards = await page.evaluate(() => document.querySelectorAll('.clip').length);
    check(`${label} (${w}px): clip grid rendered`, cards === 3, `${cards} cards`);
    const box = await page.evaluate(() => {
      const card = document.querySelector('.clip');
      const cardRect = card.getBoundingClientRect();
      const btn = sel => {
        const el = card.querySelector(sel);
        const r = el.getBoundingClientRect();
        return { x: r.x, y: r.y, w: r.width, h: r.height, r: r.right, b: r.bottom };
      };
      const cs = getComputedStyle(card.querySelector('.cactions'));
      return {
        card: { x: cardRect.x, y: cardRect.y, r: cardRect.right, b: cardRect.bottom },
        download: btn('[data-act="download-clip"]'),
        edit: btn('[data-act="edit-clip"]'),
        menu: btn('.menu > summary'),
        columns: cs.gridTemplateColumns.split(' ').length,
        gap: cs.columnGap,
        scrollW: card.scrollWidth,
        clientW: card.clientWidth
      };
    });
    const inside = b => b.x >= box.card.x - 0.5 && b.r <= box.card.r + 0.5 && b.b <= box.card.b + 0.5;
    const sameRow = (a, b) => Math.abs(a.y - b.y) < 1.5;
    const overlap = (a, b) => !(a.r <= b.x + 0.5 || b.r <= a.x + 0.5 || a.b <= b.y + 0.5 || b.b <= a.y + 0.5);

    check(`${label} (${w}px): all three controls stay inside the card`,
      inside(box.download) && inside(box.edit) && inside(box.menu),
      JSON.stringify({ card: box.card, download: box.download, menu: box.menu }));
    check(`${label} (${w}px): controls never overlap`,
      !overlap(box.download, box.edit) && !overlap(box.edit, box.menu) && !overlap(box.download, box.menu));
    check(`${label} (${w}px): no horizontal overflow inside the card`,
      box.scrollW <= box.clientW + 1, `${box.scrollW} > ${box.clientW}`);
    const onOneRow = sameRow(box.download, box.edit) && sameRow(box.edit, box.menu);
    const stacked = !sameRow(box.download, box.edit) && sameRow(box.edit, box.menu);
    check(`${label} (${w}px): ${mode === 'row' ? 'one action row' : 'Download on its own row, Edit + More under it'}`,
      mode === 'row' ? onOneRow : stacked,
      JSON.stringify({ y: [box.download.y, box.edit.y, box.menu.y] }));
    const sameHeight = Math.abs(box.download.h - box.edit.h) < 0.5
      && Math.abs(box.edit.h - box.menu.h) < 0.5;
    // In a row: Download is visibly the primary control. Stacked: it spans the
    // same full width as the Edit + More row beneath it.
    const rowWidth = box.menu.r - box.edit.x;
    const primary = mode === 'row'
      ? box.download.w >= box.edit.w * 1.2
      : Math.abs(box.download.x - box.edit.x) < 0.5
        && Math.abs(box.download.r - box.menu.r) < 0.5
        && Math.abs(box.download.w - rowWidth) < 2;
    check(`${label} (${w}px): Download is the primary control`,
      primary && box.download.h >= 28 && sameHeight,
      `${box.download.w.toFixed(0)} / ${box.edit.w.toFixed(0)} / ${box.menu.w.toFixed(0)} px wide, heights ${box.download.h}px`);
    check(`${label} (${w}px): Edit and More are equal height and aligned`,
      sameHeight && Math.abs(box.edit.b - box.menu.b) < 0.5 && Math.abs(box.edit.h - box.menu.h) < 0.5,
      `edit ${box.edit.h}px @${box.edit.y.toFixed(0)}, menu ${box.menu.h}px @${box.menu.y.toFixed(0)}`);
    if (shotDir) {
      await page.screenshot({ path: `${shotDir}/clipcard-${label}.png`, clip: {
        x: box.card.x - 6, y: box.card.y - 6,
        width: box.card.r - box.card.x + 12, height: box.card.b - box.card.y + 12 } });
      await page.screenshot({ path: `${shotDir}/page-${label}.png` });
    }
    } finally {
      await page.close();
    }
  }
} finally {
  await browser.close();
}
console.log(failures.length ? `\n${failures.length} check(s) failed` : '\nall browser checks passed');
process.exit(failures.length ? 1 : 0);
