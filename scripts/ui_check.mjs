/* DOM check for the Home option panel (no browser needed).
 *
 * The Home screen builds its controls in JavaScript, so string assertions only
 * prove a label exists. This script loads the real index.html + app.js in jsdom,
 * renders the options panel and clicks the "Force two-up" button to prove that
 * the three-way framing control renders, switches and posts a value the server
 * understands.
 *
 *   npm install jsdom          # once, anywhere on NODE_PATH
 *   node scripts/ui_check.mjs  [--jsdom path/to/jsdom/lib/api.js]
 *
 * Exits 0 when every check passes, 1 otherwise.
 */
import { readFileSync, existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const jsdomFlag = args.indexOf('--jsdom');
let jsdomPath = jsdomFlag >= 0 ? args[jsdomFlag + 1] : null;

const require = createRequire(import.meta.url);
if (!jsdomPath) {
  try {
    jsdomPath = require.resolve('jsdom');
  } catch (_) {
    for (const guess of ['node_modules/jsdom/lib/api.js', '/tmp/jsdomtest/node_modules/jsdom/lib/api.js']) {
      if (existsSync(resolve(process.cwd(), guess))) { jsdomPath = resolve(process.cwd(), guess); break; }
    }
  }
}
if (!jsdomPath || !existsSync(jsdomPath)) {
  console.error('jsdom not found - run: npm install jsdom');
  process.exit(2);
}
const { JSDOM } = await import(jsdomPath);

const html = readFileSync(`${repo}/marrow/web/index.html`, 'utf8');
const js = readFileSync(`${repo}/marrow/web/app.js`, 'utf8');

const dom = new JSDOM(html, { runScripts: 'dangerously', url: 'http://localhost:8137/#/', pretendToBeVisual: true });
const { window } = dom;
window.fetch = () => new Promise(() => {});            // never resolves: we never need the API
window.EventSource = class { addEventListener() {} close() {} };
window.matchMedia = q => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
window.HTMLMediaElement.prototype.play = () => Promise.resolve();
window.HTMLMediaElement.prototype.pause = () => {};

const failures = [];
const check = (name, ok, detail = '') => {
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${name}${detail ? ' - ' + detail : ''}`);
  if (!ok) failures.push(name);
};

const boot = window.document.createElement('script');
boot.textContent = `try {
${js}
window.__api = { optsPanel, readOpts, modeOf, speakerModeHTML, updateHomePreview };
} catch (err) { window.__err = err && (err.stack || String(err)); }`;
window.document.head.appendChild(boot);
check('app.js loads without throwing', !window.__err, window.__err || '');
if (window.__err) { process.exit(1); }
const api = window.__api;

const opts = extra => Object.assign({
  platform: 'shorts', layout: 'crop', clips: 5, duration: 45, captions: true,
  use_llm: false, zoom: false, caption_style: { preset: 'bold-pop', overrides: {} }
}, extra);

const render = extra => {
  const host = window.document.createElement('div');
  host.innerHTML = api.optsPanel(opts(extra), true);
  return host;
};

const twoUp = render({ speaker_mode: 'two_up' });
const seg = twoUp.querySelector('[data-opt="split_screen"]');
check('framing control postings the legacy key', !!seg);
check('three modes are offered', seg && [...seg.querySelectorAll('button')].map(b => b.dataset.v).join(',') === 'auto,two_up,off');
check('saved two-up mode is selected', !!twoUp.querySelector('[data-v="two_up"].on'));
check('card explains the mode', /Force two-up/.test(twoUp.querySelector('.speaker-mode .tl b').textContent));

const legacyOff = render({ split_screen: false });
check('legacy split_screen:false maps to Off', legacyOff.querySelector('.speaker-mode').dataset.mode === 'off');

const legacyOn = render({ split_screen: true });
check('legacy split_screen:true maps to Auto', legacyOn.querySelector('.speaker-mode').dataset.mode === 'auto');

check('modeOf understands aliases', api.modeOf({ speaker_mode: 'force-two-up' }) === 'two_up'
  && api.modeOf({ split_screen: 0 }) === 'off' && api.modeOf({}) === 'auto');

const host = window.document.createElement('div');
host.id = 'optbox';
host.innerHTML = api.optsPanel(opts({ speaker_mode: 'auto' }), true);
window.document.body.appendChild(host);
host.querySelector('[data-v="two_up"]').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
check('clicking Force two-up posts it', api.readOpts(host).split_screen === 'two_up',
  `got ${JSON.stringify(api.readOpts(host).split_screen)}`);
check('clicking updates the card copy',
  host.querySelector('.speaker-mode').dataset.mode === 'two_up'
  && /Force two-up/.test(host.querySelector('.speaker-mode .tl b').textContent));

console.log(failures.length ? `\n${failures.length} check(s) failed` : '\nall UI checks passed');
process.exit(failures.length ? 1 : 0);
