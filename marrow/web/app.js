'use strict';
/* ---------- icons: inline SVG (emoji look different on every OS, so none are used) ---------- */
const ICON = {
  home: '<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  pen: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
  download: '<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/>',
  upload: '<path d="M12 16V4"/><path d="m7 9 5-5 5 5"/><path d="M5 20h14"/>',
  trash: '<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/>',
  play: '<path d="M7 4.5v15l12-7.5z"/>',
  pause: '<rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/>',
  expand: '<path d="M15 3h6v6"/><path d="M9 21H3v-6"/><path d="M21 3l-7 7"/><path d="M3 21l7-7"/>',
  copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  more: '<circle cx="5" cy="12" r="1.7"/><circle cx="12" cy="12" r="1.7"/><circle cx="19" cy="12" r="1.7"/>',
  back: '<path d="M19 12H5"/><path d="m12 19-7-7 7-7"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-2.6-6.3L21 8"/><path d="M21 3v5h-5"/>',
  external: '<path d="M14 3h7v7"/><path d="M10 14 21 3"/><path d="M21 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  minus: '<path d="M5 12h14"/>',
  alert: '<circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16.5v.5"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  film: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4"/>',
  sparkle: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>',
  type: '<path d="M4 7V4h16v3"/><path d="M9 20h6"/><path d="M12 4v16"/>',
  lock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  unlock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 7.7-1.5"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/>',
  redo: '<path d="m15 14 5-5-5-5"/><path d="M20 9H9a5 5 0 0 0 0 10h3"/>',
  chevL: '<path d="m15 18-6-6 6-6"/>',
  chevR: '<path d="m9 18 6-6-6-6"/>',
};
const ico = (n, c = '') => `<svg class="i ${c}" viewBox="0 0 24 24" aria-hidden="true">${ICON[n] || ''}</svg>`;

/* ---------- theme & accent (the sidebar button is the quick toggle; Settings has the full choice) ---------- */
const themeChoice = () => { try { return localStorage.getItem('theme') || 'system'; } catch (_) { return 'system'; } };
const sysLight = () => matchMedia('(prefers-color-scheme: light)').matches;
function paintThemeBtn() {
  const b = document.getElementById('themeBtn'); if (!b) return;
  const light = document.documentElement.dataset.theme === 'light';
  b.innerHTML = `${ico(light ? 'moon' : 'sun')}<span>${light ? 'Dark mode' : 'Light mode'}</span>`;
}
function setTheme(t) {
  const choice = t || 'system';
  document.documentElement.dataset.theme = choice === 'system' ? (sysLight() ? 'light' : 'dark') : choice;
  document.documentElement.dataset.themeChoice = choice;
  try { localStorage.setItem('theme', choice); } catch (_) {}
  paintThemeBtn();
}
function setAccent(a) {
  const v = a && a !== 'graphite' ? a : '';
  if (v) document.documentElement.dataset.accent = v; else delete document.documentElement.dataset.accent;
  try { localStorage.setItem('accent', v || 'graphite'); } catch (_) {}
}
setTheme(themeChoice());
let _accent = 'graphite';
try { _accent = localStorage.getItem('accent') || 'graphite'; } catch (_) {}
setAccent(_accent);
document.getElementById('themeBtn').addEventListener('click', () => {
  setTheme(document.documentElement.dataset.theme === 'light' ? 'dark' : 'light');
});
matchMedia('(prefers-color-scheme: light)').addEventListener?.('change', () => { if (themeChoice() === 'system') setTheme('system'); });
let custOpen = false;
try { custOpen = (localStorage.getItem('custOpen') || '') === '1'; } catch (_) {}
document.addEventListener('toggle', e => {
  if (e.target.matches?.('details.cust')) { try { localStorage.setItem('custOpen', e.target.open ? '1' : ''); } catch (_) {} }
}, true);
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const ACTIVE = new Set(['queued', 'running']);
const state = { projects: [], system: null, settings: null, pending: null, uploadPct: null, url: '', opts: null, route: null };

/* ---------- api / utils ---------- */
async function api(path, o = {}) {
  const init = { method: o.method || 'GET', headers: { 'X-Marrow': '1' } };
  if (o.body !== undefined) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(o.body); }
  const r = await fetch(path, init);
  let data = null; try { data = await r.json(); } catch (_) {}
  if (!r.ok) throw new Error((data && data.error) || ('Request failed (' + r.status + ')'));
  return data;
}
function toast(msg, kind = '') {
  const t = document.createElement('div'); t.className = 'toast ' + kind; t.textContent = msg;
  $('#toasts').appendChild(t); setTimeout(() => t.remove(), kind === 'bad' ? 7000 : 3500);
}
function toastLink(html) {
  const t = document.createElement('div'); t.className = 'toast ok'; t.innerHTML = html;
  $('#toasts').appendChild(t); setTimeout(() => t.remove(), 8000);
}
let _ac = null;
function ac() {
  try {
    if (!_ac) _ac = new (window.AudioContext || window.webkitAudioContext)();
    if (_ac.state === 'suspended') _ac.resume();
  } catch (_) { _ac = null; }
  return _ac;
}
document.addEventListener('pointerdown', () => ac());
function wavBytes(buf) {
  const d = buf.getChannelData(0), n = d.length, ab = new ArrayBuffer(44 + n * 2), v = new DataView(ab);
  const ws = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  ws(0, 'RIFF'); v.setUint32(4, 36 + n * 2, true); ws(8, 'WAVE'); ws(12, 'fmt ');
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, buf.sampleRate, true); v.setUint32(28, buf.sampleRate * 2, true);
  v.setUint16(32, 2, true); v.setUint16(34, 16, true); ws(36, 'data'); v.setUint32(40, n * 2, true);
  for (let i = 0; i < n; i++) v.setInt16(44 + i * 2, Math.max(-1, Math.min(1, d[i])) * 32767, true);
  return new Blob([ab], { type: 'audio/wav' });
}
function beepFallback() {
  try {
    const Ctx = window.OfflineAudioContext || window.webkitOfflineAudioContext;
    if (!Ctx) return;
    const sr = 16000, ctx = new Ctx(1, Math.floor(sr * 0.45), sr);
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.type = 'sine'; o.frequency.value = 880;
    g.gain.setValueAtTime(0.0001, 0);
    g.gain.exponentialRampToValueAtTime(0.25, 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, 0.44);
    o.connect(g).connect(ctx.destination); o.start(); o.stop(0.45);
    ctx.startRendering().then(buf => {
      const a = document.createElement('audio');
      a.src = URL.createObjectURL(wavBytes(buf));
      a.play().catch(() => {});
    }).catch(() => {});
  } catch (_) {}
}
function doneBeep() {
  const ctx = ac();
  if (ctx) {
    try {
      const o = ctx.createOscillator(), g = ctx.createGain();
      o.type = 'sine'; o.frequency.value = 880;
      g.gain.setValueAtTime(0.0001, ctx.currentTime);
      g.gain.exponentialRampToValueAtTime(0.25, ctx.currentTime + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.45);
      o.connect(g).connect(ctx.destination);
      o.start(); o.stop(ctx.currentTime + 0.5);
      return;
    } catch (_) {}
  }
  beepFallback();
}
function soundOn() { try { return (localStorage.getItem('soundFinish') || 'on') === 'on'; } catch (_) { return true; } }
function shouldBeep() { return document.visibilityState === 'visible' || soundOn(); }
function onJobDone(p) {
  if (shouldBeep()) doneBeep();   // never beeps on error: only called for done
  document.title = '✓ Marrow — done';
  window.addEventListener('focus', () => { document.title = 'Marrow'; }, { once: true });
  if (window.Notification && Notification.permission === 'granted') {
    try { new Notification('Marrow — clips ready', { body: `${p.clips.length} clips ready for "${p.name}"` }); } catch (_) {}
  }
  toastLink(`Clips ready · <a href="#/p/${p.id}" style="text-decoration:underline">View</a>`);
}
const fmtT = s => { s = Math.max(0, Math.round(s)); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60;
  return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(x).padStart(2, '0'); };
const fmtDate = t => t ? new Date(t * 1000).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';
const platLabel = p => p === 'both' ? 'Shorts + Reels' : p === 'reels' ? 'Reels' : 'Shorts';
const hasActive = () => state.projects.some(p => ACTIVE.has(p.status) || p.clips.some(c => c.status === 'rendering'));
async function copyText(text, okMsg) {
  try { await navigator.clipboard.writeText(text); }
  catch (_) { const t = document.createElement('textarea'); t.value = text; document.body.appendChild(t); t.select(); document.execCommand('copy'); t.remove(); }
  toast(okMsg, 'ok');
}

/* ---------- modal ---------- */
function openModal(html, wide) {
  closeModal();
  const b = document.createElement('div'); b.className = 'backdrop';
  b.innerHTML = '<div class="modal' + (wide ? ' wide' : '') + '">' + html + '</div>';
  b.addEventListener('mousedown', e => { if (e.target === b) closeModal(); });
  $('#modal-root').appendChild(b); return b.firstChild;
}
function closeModal() { const r = $('#modal-root'); const v = $('video', r); if (v) v.pause(); r.innerHTML = ''; editCtx = null; pvDetachBig(); pvLive(); }
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
function confirmBox({ title, text, ok = 'Confirm', danger = false, check = null }) {
  return new Promise(res => {
    const m = openModal(`<h3>${esc(title)}</h3><p class="desc">${esc(text)}</p>
      ${check ? `<label class="chk"><input type="checkbox" id="cb-check"><span><span class="t">${esc(check)}</span></span></label>` : ''}
      <div class="mfoot"><button class="btn ghost" id="cb-no">Cancel</button><button class="btn ${danger ? 'danger' : 'primary'}" id="cb-yes">${esc(ok)}</button></div>`);
    $('#cb-no', m).onclick = () => { closeModal(); res({ ok: false }); };
    $('#cb-yes', m).onclick = () => { const c = $('#cb-check', m); closeModal(); res({ ok: true, checked: !!(c && c.checked) }); };
  });
}

/* ---------- option controls (shared by Home + Regenerate) ---------- */
const seg = (key, items, val) => `<div class="seg" data-opt="${key}">${items.map(([v, l]) =>
  `<button type="button" class="${v === val ? 'on' : ''}" data-v="${v}" data-act="seg">${l}</button>`).join('')}</div>`;
const tog = (key, label, on, hint) => `<label class="tog"><input type="checkbox" data-opt="${key}" ${on ? 'checked' : ''}><span class="knob"></span><span class="tl">${label}${hint ? `<small>${hint}</small>` : ''}</span></label>`;
function customizeHTML(ov, presetKey) {
  ov = capNorm(ov);                                   // touched values only (font_size from older saves reads as size)
  const e = resolveCap(presetKey, ov);                // what the renderer will use, shown wherever nothing is overridden
  const has = k => ov[k] !== undefined && ov[k] !== null && ov[k] !== '';
  const T = k => (has(k) ? ' data-touched="1"' : '');
  const word = e.display === 'word';
  const fams = ['Arial', ...new Set(Object.values(STYLES.presets || {}).flatMap(x => [x.font, x.font_ar]).filter(Boolean))];
  if (has('font') && !fams.includes(ov.font)) fams.push(ov.font);
  const ovSeg = (key, items, val, dense, touched) => `<div class="seg${dense ? ' dense' : ''}" data-ov="${key}"${touched ? ' data-touched="1"' : ''}>${items.map(([v, l]) =>
    `<button type="button" class="${String(v) === String(val) ? 'on' : ''}" data-v="${v}" data-act="seg">${l}</button>`).join('')}</div>`;
  const color = (key, label) => `<div class="cell"><label>${label}</label><div class="row"><input type="color" data-ov="${key}" value="${e[key]}"${T(key)}><span class="hint mono">${has(key) ? ov[key] : ''}</span></div></div>`;
  const wcols = [0, 1, 2].map(i => (e.word_colors && e.word_colors[i]) || e.highlight_color);
  const touchedAny = Object.keys(ov).some(k => has(k));
  return `<div class="cfg2">
    <div class="cell"><label>Text size</label><div class="row"><input type="range" min="40" max="110" data-ov="size" data-unit=""${T('size')} value="${e.size}"><output>${has('size') ? e.size : 'auto'}</output></div></div>
    <div class="cell"><label>Uppercase</label><label class="tog compact"><input type="checkbox" data-ov="uppercase"${T('uppercase')} ${e.uppercase ? 'checked' : ''}><span class="knob"></span></label></div>
    <div class="cell"><label>Display</label>${ovSeg('display', [['line', 'Line'], ['word', 'Word']], word ? 'word' : 'line', false, has('display'))}</div>
    <div class="cell"><label>Font</label><select data-ov="font"${T('font')}><option value="">Style default</option>${fams.map(f => `<option ${has('font') && f === ov.font ? 'selected' : ''}>${f}</option>`).join('')}</select></div>
    <div class="cell"><label>Outline</label>${ovSeg('outline', [['', 'Auto'], ...[0, 1, 2, 3, 4, 5, 6, 7, 8].map(n => [n, String(n)])], has('outline') ? ov.outline : '', true, has('outline'))}</div>
    <div class="cell"><label>Words per line</label>${ovSeg('max_words_per_line', [['', 'Auto'], [1, '1'], [2, '2'], [3, '3']], has('max_words_per_line') ? ov.max_words_per_line : '', false, has('max_words_per_line'))}</div>
    <div class="cell"><label>Position</label>${ovSeg('position', [['lower', 'Bottom'], ['center', 'Center'], ['top', 'Top']], e.position, false, has('position'))}</div>
    <div class="cell"><label>Pop animation</label><label class="tog compact"><input type="checkbox" data-ov="anim_pop"${T('anim')} ${e.anim === 'none' ? '' : 'checked'}><span class="knob"></span></label></div>
    ${color('highlight_color', 'Highlight color')}
    ${color('text_color', 'Text color')}
    <div class="cell" data-word-only${word ? '' : ' hidden'}><label>Word colors</label><div class="wcols">${wcols.map(c => `<input type="color" data-ov-list="word_colors" value="${c}"${T('word_colors')}>`).join('')}</div></div>
    <div class="cell" data-word-only${word ? '' : ' hidden'}><label>Strip punctuation</label><label class="tog compact"><input type="checkbox" data-ov="strip_punct"${T('strip_punct')} ${e.strip_punct === false ? '' : 'checked'}><span class="knob"></span></label></div>
  </div>
  <div class="cust-foot" data-cust-foot${touchedAny ? '' : ' hidden'}><button type="button" class="btn ghost sm" data-act="cust-reset">Reset to preset</button></div>`;
}
/* Home's caption-style block: the preset carousel, and the live 9:16 phone on the right (the caption preview engine). */
function styleSectionHTML(preset) {
  return stylePickerHTML(preset, '<div class="phone pv" id="homePhone"></div>');
}
function optsPanel(o, compact) {
  const cs = o.caption_style || { preset: 'bold-pop', overrides: {} };
  const ov = cs.overrides || {};
  const s = state.system;
  const ready = !!(s && s.ollama.reachable && s.ollama.model_ready);
  const llmHint = !s ? 'Checking Ollama…'
    : ready ? 'Ready: judges hook, payoff and clarity'
    : s.ollama.reachable ? `Model “${esc(s.ollama.model)}” isn’t pulled yet, so heuristics are used`
    : 'Ollama isn’t running, so heuristics are used';
  const dur = o.duration || 45;
  return `<div class="optbody">
    <div class="opt-group"><span class="fl">Output</span>${seg('platform', [['shorts', 'Shorts'], ['reels', 'Reels'], ['both', 'Both']], o.platform)}</div>
    <div class="opt-group"><span class="fl">Framing</span>${seg('layout', [['crop', 'Center crop'], ['blur_fit', 'Blur fit']], o.layout)}</div>
    <div class="opt-group"><span class="fl">Number of clips</span>
      <div class="stepper"><button type="button" class="icon sm" data-step="clips" data-d="-1" aria-label="Fewer clips">${ico('minus')}</button>
        <input type="number" min="1" max="20" data-opt="clips" value="${o.clips || 5}" aria-label="Number of clips"><button type="button" class="icon sm" data-step="clips" data-d="1" aria-label="More clips">${ico('plus')}</button></div></div>
    <div class="opt-group"><div class="row-between"><span class="fl">Target length</span><output class="val">${dur}s</output></div>
      <input type="range" min="15" max="180" step="5" data-opt="duration" data-unit="s" value="${dur}" aria-label="Target length in seconds"></div>
    <div class="opt-group toggles">
      ${tog('captions', 'Animated captions', o.captions, 'Word-by-word captions burned into the video')}
      ${tog('use_llm', 'AI clip scoring', o.use_llm, llmHint)}
      ${tog('zoom', 'Slow zoom', o.zoom, 'Gentle push-in (center crop only, renders slower)')}
    </div>
    ${compact ? '' : `<div class="opt-group full"><span class="fl">Caption style</span>
      ${stylePickerHTML(cs.preset, `<div class="capprev-wrap"><img class="capprev capPrev" alt="" hidden><p class="hint capPrevNote">Pick a style to preview it on your video</p></div>`)}</div>
    <div class="opt-group full"><details class="cust"><summary>Customize style</summary><div class="custwrap">${customizeHTML(ov, cs.preset)}</div></details></div>`}
  </div>`;
}
function readStyleRoot(root) {
  const o = { preset: $('.stylePreset', root)?.value || 'bold-pop', overrides: {} };
  if (!root) return o;
  $$('[data-ov]', root).forEach(el => {
    if (el.dataset.touched !== '1') return;           // only what the user changed: a preset keeps its own look
    const k = el.dataset.ov;
    if (k === 'anim_pop') { o.overrides.anim = el.checked ? 'pop' : 'none'; return; }
    let v;
    if (el.classList.contains('seg')) v = $('.on', el)?.dataset.v;
    else if (el.type === 'checkbox') v = el.checked;
    else if (el.type === 'range' || el.type === 'number') v = el.value !== '' ? Number(el.value) : undefined;
    else if (el.value !== '') v = el.value;
    if (typeof v === 'string' && /^\d+$/.test(v)) v = Number(v);      // Outline and Words per line are numbers
    if (v === undefined || v === null || v === '') return;   // "Auto" and "Style default" mean no override
    o.overrides[k] = v;
  });
  const wc = $$('[data-ov-list="word_colors"]', root);
  if (wc.some(el => el.dataset.touched === '1')) {
    const cols = wc.map(el => el.value).filter(Boolean).slice(0, 6);
    if (cols.length) o.overrides.word_colors = cols;
  }
  return o;
}

/* "Your plan": a plain-language summary of the current compact settings. */
function paintPlan() {
  const box = document.getElementById('planBox'); if (!box || !document.getElementById('optbox')) return;
  const o = readOpts(document.getElementById('optbox'));
  const preset = document.querySelector('#styleCard .stylePreset')?.value || state.opts?.caption_style?.preset || 'bold-pop';
  const label = STYLES.presets?.[preset]?.label || preset;
  const fmt = { shorts: 'YouTube Shorts · 9:16', reels: 'Facebook Reels · 9:16', both: 'Shorts + Reels' }[o.platform] || 'YouTube Shorts · 9:16';
  const frame = o.layout === 'blur_fit' ? 'Blur fit' : 'Center crop';
  const rows = [
    ['Clips', `${o.clips || 1} × about ${o.duration || 45} s`],
    ['Format', fmt],
    ['Framing', frame + (o.zoom ? ' · slow zoom' : '')],
    ['Captions', o.captions ? label : 'Off'],
    ['Scoring', o.use_llm ? 'AI, with a heuristic fallback' : 'Heuristics only'],
  ];
  box.innerHTML = `<span class="label">Your plan</span><dl>${rows.map(([k, v]) => `<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>`;
}
function readOpts(root) {
  const o = { caption_style: readStyleRoot(root) };
  if (!root) return o;
  $$('[data-opt]', root).forEach(el => {
    const k = el.dataset.opt; let v;
    if (el.classList.contains('seg')) v = $('.on', el)?.dataset.v;
    else if (el.type === 'checkbox') v = el.checked;
    else if (el.type === 'range' || el.type === 'number') v = Number(el.value);
    else v = el.value;
    o[k] = v;
  });
  return o;
}
/* ---------- caption style picker (shared by Home, Regenerate, Edit modal) ---------- */
const SAMPLES = { en: ['MAKE', 'IT', 'GO', 'VIRAL'], ar: ['اجعل', 'فيديوك', 'ينتشر', 'الآن'] };
let STYLES = { base: {}, presets: {} }, sampleLang = 'en', tickIdx = 0;
/* Hardcoded fallback so the carousel never renders blank (used until /api/caption-styles loads, or if it fails) */
const FALLBACK_BASE = { font: 'Arial', font_ar: 'Arial', size: 72, bold: true, uppercase: true,
  text_color: '#FFFFFF', highlight_color: '#FFE600', outline_color: '#000000', outline: 4, shadow: 2,
  highlight_mode: 'color', pill_color: '#FFFFFF', pill_text: '#000000', active_scale: 110 };
const FALLBACK_PRESETS = {
  'bold-pop': { label: 'Bold Pop', font: 'Montserrat', highlight_color: '#FFE600' },
  'hormozi': { label: 'Hormozi', font: 'Anton', highlight_color: '#00F060' },
  'beast': { label: 'Beast', font: 'Bebas Neue', highlight_color: '#FF3B30' },
  'clean': { label: 'Clean', font: 'Poppins', highlight_color: '#A78BFA' },
  'pill': { label: 'Pill', font: 'Poppins', highlight_color: '#FFFFFF' },
  'neon': { label: 'Neon', font: 'Poppins', highlight_color: '#22E5FF' },
  'box': { label: 'Box', font: 'Inter', highlight_color: '#FFD60A' },
};
STYLES = { base: FALLBACK_BASE, presets: FALLBACK_PRESETS };
function injectFonts(presets) {
  const seen = new Set(); let css = '';
  Object.values(presets).forEach(p => [[p.font, p.font_file], [p.font_ar, p.font_ar_file]].forEach(([fam, file]) => {
    if (fam && file && !seen.has(fam)) { seen.add(fam); css += `@font-face{font-family:'${fam}';src:url('/fonts/${file}')}`; }
  }));
  document.head.insertAdjacentHTML('beforeend', `<style>${css}</style>`);
}
function wordSpans(p, lang) {
  const ar = lang === 'ar';
  return SAMPLES[lang].map(w => `<span class="w" data-hl="${p.highlight_color}" data-pill="${p.highlight_mode === 'pill' ? p.pill_color : ''}" data-pt="${p.pill_text}" data-sc="${p.active_scale}" style="color:${p.text_color}">${ar || !p.uppercase ? w : w.toUpperCase()}</span>`).join(' ');
}
function prevStyle(p) {
  const fam = (sampleLang === 'ar' ? p.font_ar : p.font) || 'Arial';
  const stroke = p.outline ? `-webkit-text-stroke:1px ${p.outline_color};paint-order:stroke fill;` : '';
  const shadow = p.shadow ? `text-shadow:0 1px 2px #000a;` : '';
  const boxed = p.box ? `background:${p.box_color};padding:0 .3em;border-radius:.2em;` : '';
  return `font-family:'${fam}',Arial;font-weight:${p.bold ? 700 : 400};${stroke}${shadow}${boxed}`;
}
function prevWords(p) {
  return p.display === 'word'
    ? `<span class="w solo" data-words="${SAMPLES[sampleLang].join(',')}" data-hl="${p.highlight_color}" data-pill="${p.highlight_mode === 'pill' ? p.pill_color : ''}" data-pt="${p.pill_text}" data-sc="115" style="color:${p.highlight_color}">${SAMPLES[sampleLang][0]}</span>`
    : wordSpans(p, sampleLang);
}
function cardHTML(key, p0, base, sel) {
  const p = { ...base, ...p0 };
  const cls = `${p.box ? 'has-box' : ''} ${p.highlight_mode === 'pill' ? 'is-pill' : ''}`.trim();
  return `<div class="scard preset-card ${key === sel ? 'sel active' : ''}" data-k="${key}" title="${esc(p0.label || key)}">
    <div class="cap card-preview ${cls}" style="color:${p.text_color};${prevStyle(p)}">${prevWords(p)}</div>
    <div class="card-label">${esc(p0.label || key)}</div></div>`;
}
function tplCardHTML(t, i, sel) {
  const p0 = STYLES.presets[t.preset] || {};
  const p = { ...STYLES.base, ...p0, ...(t.overrides || {}) };
  const cls = `${p.box ? 'has-box' : ''} ${p.highlight_mode === 'pill' ? 'is-pill' : ''}`.trim();
  return `<div class="scard preset-card ${t.preset === sel ? 'sel active' : ''}" data-tpl="${i}" data-k="${esc(t.preset || 'bold-pop')}" title="${esc(t.name)}">
    <button class="tplx" data-tpldel="${i}" title="Delete template">×</button>
    <div class="cap card-preview ${cls}" style="color:${p.text_color};${prevStyle(p)}">${prevWords(p)}</div>
    <div class="card-label">${esc(t.name)}</div></div>`;
}
const TPL_KEY = 'marrow_templates';
const getTpls = () => { try { return JSON.parse(localStorage.getItem(TPL_KEY)) || []; } catch (_) { return []; } };
const setTpls = t => { try { localStorage.setItem(TPL_KEY, JSON.stringify(t)); } catch (_) {} };
/* Shared style picker: tabs + EN/AR switch, a horizontal preset carousel, and an optional preview slot. */
function stylePickerHTML(preset, preview, hiddenAttrs) {
  return `<input type="hidden" class="stylePreset" ${hiddenAttrs || ''} value="${esc(preset || 'bold-pop')}">
  <div class="style-head">
    <div class="preset-tabs" role="tablist"><button type="button" data-st="quick" class="on">Quick presets</button><button type="button" data-st="my">My templates</button></div>
    <div class="seg sm sampleLang"><button type="button" data-l="en" class="on">English</button><button type="button" data-l="ar">العربية</button></div>
  </div>
  <div class="style-body">
    <div class="style-left">
      <div class="carousel">
        <button type="button" class="car-arrow" data-car="-1" aria-label="Previous styles">${ico('chevL')}</button>
        <div class="styles styleGrid carousel-track"></div>
        <button type="button" class="car-arrow" data-car="1" aria-label="Next styles">${ico('chevR')}</button>
      </div>
    </div>
    <div class="style-right">${preview || ''}</div>
  </div>`;
}
function scrollCarousel(direction) {
  const track = document.querySelector('.carousel-track');
  if (track) track.scrollBy({ left: direction * 250, behavior: 'smooth' });
}
/* ---------- live caption preview ----------
   One engine draws the look the renderer burns in (captioner.py) and the framing it uses (renderer.py).
   Every control in Caption style and Clip settings updates it at once: before any video is found, and with
   no server round trip. The phone beside the style picker and the enlarged view are two instances. The Edit
   modal and the Edits page put the same caption layer over the real video (PvOverlay), timed by its clock. */
const CAP_BASE = {                                   // mirrors caption_styles.BASE; the server's copy wins once loaded
  font: 'Arial', font_ar: 'Arial', size: 72, bold: true, italic: false, uppercase: true,
  text_color: '#FFFFFF', highlight_color: '#FFE600', outline_color: '#000000', outline: 4, shadow: 2, blur: 0,
  box: false, box_color: '#000000', box_opacity: 60, highlight_mode: 'color', pill_color: '#FFFFFF',
  pill_text: '#000000', pill_pad: 10, active_scale: 110, emphasis_scale: 125, anim: 'pop', display: 'line',
  word_colors: null, strip_punct: true, min_gap: 0.22, position: 'lower', max_words_per_line: 4, max_chars_per_line: 22,
};
const PV_SAMPLE = {                                  // a sample phrase; its punctuation shows where lines break
  en: ['make', 'it', 'go', 'viral,', 'right', 'now.'],
  ar: ['اجعل', 'فيديوك،', 'ينتشر', 'الآن.', 'ويصل', 'للجميع'],
};
const PV_ENERGY = [0.3, 0.2, 0.6, 0.95, 0.45, 0.8];  // stand-in word energies: the top 15% get the emphasis scale
const PV_MARGIN = { shorts: 420, reels: 460 };       // caption_margin_v, used until /api/caption-styles answers
const PV_TICK_MS = 400;                              // one sample word per tick
const PUNCT_BREAK = /[,.?!;:…،؛؟]$/;                  // captioner.PUNCT_BREAK: a line may end after these
const PUNCT_STRIP = /^[.,!?;:…،؛؟]+|[.,!?;:…،؛؟]+$/g; // captioner: punctuation removed in word mode when strip_punct is on

/* The style the renderer uses: BASE < config captions < preset < touched overrides (caption_styles.resolve_style). */
function capNorm(d) {
  const o = { ...(d || {}) };
  if ('font_size' in o) { if (o.size == null) o.size = o.font_size; delete o.font_size; }
  return o;
}
function resolveCap(presetKey, ov) {
  const base = { ...CAP_BASE, ...(STYLES.base || {}) };
  const st = { ...base };
  const take = src => {
    if (!src) return;
    for (const k of Object.keys(base)) { const v = src[k]; if (v !== undefined && v !== null && v !== '') st[k] = v; }
  };
  take(capNorm(STYLES.legacy));
  take(STYLES.presets && STYLES.presets[presetKey]);
  take(capNorm(ov));
  return st;
}
/* libass sizes a style's Fontsize to the font's height (OS/2 win ascent + descent), not to its em: see caption_styles.font_height_em */
const pvFontH = fam => { const m = STYLES.font_height || {}; return m[fam] || m.Arial || 1.117; };
const pvMargin = platform => (STYLES.margins || PV_MARGIN)[platform === 'reels' ? 'reels' : 'shorts'] ?? PV_MARGIN.shorts;
function pvPercentile(xs, p) {                       // numpy's default (linear) percentile, as captioner.py uses
  const a = [...xs].sort((x, y) => x - y);
  if (!a.length) return Infinity;
  const pos = p / 100 * (a.length - 1), lo = Math.floor(pos), hi = Math.ceil(pos);
  return a[lo] + (a[hi] - a[lo]) * (pos - lo);
}
const PV_GAP = 0.6;                                  // captioner.group_words: a line breaks after a pause longer than this
/* captioner.group_words: a line ends at the word or character limit, after a pause longer than `gap`, or after punctuation */
function pvGroup(words, maxW, maxC, gap) {
  const lines = []; let cur = [], chars = 0;
  for (const w of words) {
    let extra = w.raw.length + (cur.length ? 1 : 0);
    if (cur.length && (cur.length >= maxW || chars + extra > maxC || w.s - cur[cur.length - 1].e > gap)) {
      lines.push(cur); cur = []; chars = 0; extra = w.raw.length;
    }
    cur.push(w); chars += extra;
    if (PUNCT_BREAK.test(w.raw) && cur.length >= 2) { lines.push(cur); cur = []; chars = 0; }
  }
  if (cur.length) lines.push(cur);
  return lines;
}
/* captioner._finalize: sorted by start, overlaps clamped, empty events dropped */
function pvFinalize(ev) {
  const out = [];
  for (const x of ev.slice().sort((a, b) => a.s - b.s || a.e - b.e)) {
    const p = out[out.length - 1];
    if (p && x.s < p.e - 1e-9) p.e = Math.max(p.s + 0.02, Math.min(p.e, x.s));
    out.push({ ...x });
  }
  return out.filter(x => x.e > x.s + 1e-9);
}
const PV_RTL = /[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]/g;   // captioner._AR
function pvIsRtl(words) {                            // captioner.is_rtl: most of the text is Arabic script
  const txt = words.map(w => String(w.t)).join('');
  return !!txt && (txt.match(PV_RTL) || []).length > txt.length / 2;
}
function hexA(hex, opacityPct) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || '');
  const n = m ? parseInt(m[1], 16) : 0;
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${(opacityPct / 100).toFixed(2)})`;
}
/* The shape of the caption: lines of units (Line mode), or one unit at a time (Word mode). `events` only exist for
   timed text: the position of the unit lit at each stretch of the clip. */
function pvLineModel(units, lines, palette, st) {
  const lineOf = [];
  lines.forEach((ln, li) => ln.forEach(w => { lineOf[w.pos] = li; }));
  return { isWord: false, units, lines, lineOf, palette, pill: st.highlight_mode === 'pill', pop: st.anim === 'pop', events: null };
}
function pvSampleModel(lang, st) {                   // the sample phrase on Home: one word per tick
  const rtl = lang === 'ar', up = !!st.uppercase && !rtl;
  const raw = PV_SAMPLE[lang] || PV_SAMPLE.en;
  const palette = st.word_colors && st.word_colors.length ? st.word_colors : [st.highlight_color];
  if (st.display === 'word') {
    const units = raw.map((t, pos) => {
      const txt = st.strip_punct === false ? t : t.replace(PUNCT_STRIP, '');
      return { pos, text: up ? txt.toUpperCase() : txt };
    });
    return { isWord: true, units, lines: [], lineOf: [], palette, pill: false, pop: st.anim === 'pop', events: null };
  }
  const thr = pvPercentile(PV_ENERGY, 85);
  const ws = raw.map((t, pos) => ({
    pos, raw: t, text: up ? t.toUpperCase() : t, s: pos * PV_TICK_MS / 1000, e: (pos + 1) * PV_TICK_MS / 1000,
    sc: (PV_ENERGY[pos] >= thr ? st.emphasis_scale : st.active_scale) / 100,
  }));
  return pvLineModel(ws, pvGroup(ws, st.max_words_per_line || 4, st.max_chars_per_line || 22, PV_GAP), palette, st);
}
/* Word mode, as generate_ass lays it out: words that start within min_gap (up to four) share one event. */
function pvWordModel(ws, st, up, palette) {
  const gap = +st.min_gap || 0.22;
  const clusters = []; let cur = [];
  for (const w of ws) {
    if (cur.length && w.s - cur[0].s < gap && cur.length < 4) cur.push(w);
    else { if (cur.length) clusters.push(cur); cur = [w]; }
  }
  if (cur.length) clusters.push(cur);
  const units = [], ev = [];
  clusters.forEach((cl, k) => {
    const w0 = cl[0], wl = cl[cl.length - 1];
    const nxt = k + 1 < clusters.length ? clusters[k + 1][0].s : Infinity;
    const txt = cl.map(x => (st.strip_punct === false ? x.raw : x.raw.replace(PUNCT_STRIP, ''))).join(' ');
    let end = Math.max(wl.e + 0.10, w0.s + gap);
    end = Math.max(end, w0.s + Math.min(Array.from(txt).length * 0.04, 0.5));   // long words hold longer
    if (nxt - wl.e > 0.35) end = Math.min(end + 0.15, nxt - 0.01);              // hold into pauses
    if (txt && '.,!?…،؟؛'.includes(txt[txt.length - 1])) end = Math.max(end, Math.min(w0.s + 0.25, nxt - 0.01));
    end = Math.min(Math.max(end, w0.s + 0.05), nxt !== Infinity ? nxt - 0.01 : end);
    units.push({ pos: k, text: up ? txt.toUpperCase() : txt });
    ev.push({ s: w0.s, e: end, pos: k });
  });
  return { isWord: true, units, lines: [], lineOf: [], palette, pill: false, pop: st.anim === 'pop', events: pvFinalize(ev) };
}
/* Timed text (the Edit and Edits previews): the clip's own words, lit when generate_ass would light them. */
function pvTimedModel(words, st) {
  const rtl = pvIsRtl(words), up = !!st.uppercase && !rtl;
  const palette = st.word_colors && st.word_colors.length ? st.word_colors : [st.highlight_color];
  const ws = words.map((w, pos) => ({ pos, raw: String(w.t), s: +w.s, e: +w.e, score: +w.score || 0 }));
  if (st.display === 'word') return pvWordModel(ws, st, up, palette);
  const thr = pvPercentile(ws.map(w => w.score), 85);      // the loudest 15% get the emphasis scale
  const units = ws.map(w => ({ ...w, text: up ? w.raw.toUpperCase() : w.raw, sc: (w.score >= thr ? st.emphasis_scale : st.active_scale) / 100 }));
  const m = pvLineModel(units, pvGroup(units, st.max_words_per_line || 4, st.max_chars_per_line || 22, PV_GAP), palette, st);
  const ev = [];                                       // generate_ass: a word stays lit until the next word, or 0.35 s past its end
  m.lines.forEach((ln, li) => {
    const limit = li + 1 < m.lines.length ? m.lines[li + 1][0].s : Infinity;
    ln.forEach((w, k) => {
      let end = k + 1 < ln.length ? Math.min(ln[k + 1].s, w.e + 0.35) : w.e + 0.1;
      end = Math.max(Math.min(end, limit), w.s + 0.05);
      ev.push({ s: w.s, e: end, pos: w.pos });
    });
  });
  m.events = pvFinalize(ev);
  return m;
}
/* What the phone should show right now: read from the page's own controls (single source of truth). */
function pvReadState() {
  const card = $('#styleCard'); if (!card) return null;
  const seg = key => $(`#optbox .seg[data-opt="${key}"] .on`)?.dataset.v;
  return {
    preset: $('.stylePreset', card)?.value || 'bold-pop',
    ov: readStyleRoot(card).overrides,
    lang: sampleLang,
    frame: seg('layout') === 'blur_fit' ? 'blur_fit' : 'crop',
    platform: seg('platform') || 'shorts',
    captions: $('#optbox input[data-opt="captions"]')?.checked !== false,
  };
}
/* Fonts: a family is loaded the first time it is needed, and the caption keeps the old face until the new one is
   ready, so text never flashes in a fallback. */
const pvFontSeen = new Set();
function pvFontReady(fam, wgt) {
  if (!document.fonts || !document.fonts.load) return true;
  const key = `${wgt} ${fam}`, font = `${wgt} 48px "${fam}"`;
  if (pvFontSeen.has(key)) return true;
  if (document.fonts.check(font)) { pvFontSeen.add(key); return true; }
  if (!pvFontSeen.has('loading ' + key)) {
    pvFontSeen.add('loading ' + key);
    document.fonts.load(font).catch(() => {}).then(() => { pvFontSeen.add(key); PV.ver++; pvSync(); });
  }
  return false;
}
const PV = { home: null, big: null, overlays: new Set(), media: { kind: null, src: '' }, tick: 0, ver: 0 };
let pvQueued = 0;

/* The caption layer: a `.pv-cap` box holding the lines, with one unit lit at a time. Every surface uses it, so the
   phone, the enlarged view and the Edit previews show the same text, size, colours and timing. */
class PvCaps {
  constructor(cap) {
    this.cap = cap; this.m = null; this.ck = null;
    this.lineNo = -1; this.solo = -1; this.litEl = null;
  }
  /* Face, size, line spacing, colours, outline, box, alignment and visibility from the resolved style. */
  style(s, st) {
    const cap = this.cap, cs = cap.style;
    const set = (k, v) => cs.setProperty(k, v), S = v => `calc(${v} * 100cqw / 1080)`;
    const rtl = s.lang === 'ar', fam = (rtl ? st.font_ar : st.font) || 'Arial', wgt = st.bold ? 700 : 400;
    const hEm = pvFontH(fam);
    if (pvFontReady(fam, wgt)) {                     // face, size and line spacing change together, once the face is ready
      set('--ff', `"${fam.replace(/["\\]/g, '')}", Arial, sans-serif`); set('--fw', String(wgt));
      set('--fs', S(st.size / hEm));                 // em size that gives libass's Fontsize, line by line
      set('--lh', String(hEm));                      // and its line spacing (the font height)
    }
    set('--fst', st.italic ? 'italic' : 'normal');
    const ow = st.box ? 0 : (st.outline || 0);       // libass draws a box instead of an outline in box mode
    set('--stkw', ow ? S(ow * 2) : '0px');          // stroke centred on the glyph edge: 2x gives `outline` px outside
    set('--stc', st.outline_color);
    set('--tsh', st.shadow && !st.box ? `${S(st.shadow)} ${S(st.shadow)} 0 rgba(0, 0, 0, .5)` : 'none');
    set('--tc', st.text_color); set('--hl', st.highlight_color);
    set('--pbg', st.pill_color); set('--ptc', st.pill_text); set('--ppad', S(st.pill_pad));
    set('--bxbg', hexA(st.box_color, st.box_opacity)); set('--bxpad', S(st.outline || 0));
    cap.setAttribute('dir', rtl ? 'rtl' : 'ltr');
    cap.classList.toggle('pv-box', !!st.box);
    if (st.position === 'center') { cs.top = '50%'; cs.bottom = 'auto'; cs.transform = 'translateY(-50%)'; }   // generate_ass: \an5
    else if (st.position === 'top') { cs.top = `${260 / 19.2}%`; cs.bottom = 'auto'; cs.transform = 'none'; }  // \an8
    else { cs.top = 'auto'; cs.bottom = `${pvMargin(s.platform) / 19.2}%`; cs.transform = 'none'; }           // \an2
    cap.hidden = !s.captions;
  }
  setModel(m, ck) {                                  // a new shape of text: rebuilt on the next show()
    this.m = m; this.ck = ck;
    this.lineNo = -1; this.solo = -1; this.litEl = null; this.cap.innerHTML = '';
  }
  /* Light unit `pos` (a word in Line mode, a word or group in Word mode). -1 shows nothing. */
  show(pos) {
    const m = this.m; if (!m) return;
    if (pos == null || pos < 0 || pos >= m.units.length) { this.clear(); return; }
    if (m.isWord) {
      if (this.solo === pos) return;
      this.solo = pos;
      this.cap.innerHTML = `<span class="pv-solo" style="color:${m.palette[pos % m.palette.length]}">${esc(m.units[pos].text)}</span>`;
      return;
    }
    const li = m.lineOf[pos];
    if (this.lineNo !== li) { this.lineNo = li; this.litEl = null; this.cap.innerHTML = this.lineHTML(li); }
    const next = this.cap.querySelector(`.pv-w[data-i="${pos}"]`);
    if (next !== this.litEl) this.lit(next);
  }
  clear() {
    if (this.lineNo === -1 && this.solo === -1) return;
    this.lineNo = -1; this.solo = -1; this.litEl = null; this.cap.innerHTML = '';
  }
  lineHTML(li) {
    const m = this.m;
    return `<div class="pv-line">${m.lines[li].map(w => `<span class="pv-w${m.pill ? ' pv-pill' : ''}${m.pop ? ' pv-pop' : ''}" data-i="${w.pos}" style="--sc:${w.sc}">${esc(w.text)}</span>`).join(' ')}</div>`;
  }
  /* The renderer grows a lit word's advance along with its glyphs, so its neighbours move apart. A CSS scale
     alone would bite into the spaces, so the lit word gets the same extra room (half on each side). */
  lit(el) {
    if (this.litEl) { this.litEl.classList.remove('pv-on'); this.litEl.style.marginLeft = ''; this.litEl.style.marginRight = ''; }
    this.litEl = el;
    if (!el) return;
    el.classList.add('pv-on');
    const sc = parseFloat(el.style.getPropertyValue('--sc')) || 1;
    const room = Math.max(0, (sc - 1) * el.offsetWidth / 2).toFixed(2) + 'px';
    el.style.marginLeft = room; el.style.marginRight = room;
  }
  /* After a style change the lit word is measured again: its size or face may have moved. */
  remeasure() { if (this.litEl) this.lit(this.litEl); }
}

/* A phone: the frame (blurred backdrop, real video or thumbnail, framing) with the caption layer on top. */
class PvPhone {
  constructor(root, big) {
    this.root = root; this.big = big;
    root.innerHTML = '<canvas class="pv-bg" width="54" height="96" aria-hidden="true"></canvas>'
      + '<video class="pv-fg" muted playsinline loop preload="auto" hidden></video>'
      + '<img class="pv-fg" alt="" hidden>'
      + '<p class="pv-note" hidden></p><div class="pv-cap" aria-hidden="true" hidden></div>'
      + (big ? '' : `<button type="button" class="pv-expand" data-pv-act="enlarge" aria-label="Enlarge preview" title="Enlarge preview">${ico('expand')}</button>`);
    this.bg = root.querySelector('.pv-bg'); this.v = root.querySelector('video.pv-fg');
    this.img = root.querySelector('img.pv-fg'); this.note = root.querySelector('.pv-note');
    this.caps = new PvCaps(root.querySelector('.pv-cap'));
    this.kind = null; this.src = ''; this.ar = 16 / 9; this.failed = false;
    this.s = null; this.st = null; this.key = ''; this.bgOn = false; this.looping = false; this.dead = false;
    const v = this.v;
    v.addEventListener('loadedmetadata', () => this.geom());
    v.addEventListener('loadeddata', () => { this.geom(); v.play().catch(() => {}); });
    v.addEventListener('seeked', () => this.draw());
    v.addEventListener('timeupdate', () => this.draw());
    v.addEventListener('error', () => this.fail());
    this.img.addEventListener('load', () => this.geom());
    this.img.addEventListener('error', () => this.fail());
    if (big) root.addEventListener('click', e => { if (!e.target.closest('button')) { if (v.paused) v.play().catch(() => {}); else v.pause(); } });
  }
  destroy() {
    this.dead = true; this.v.pause(); this.v.removeAttribute('src'); this.v.load(); this.img.removeAttribute('src');
  }
  fail() { this.setMedia(null, ''); this.failed = true; this.paintNote(); }
  setMedia(kind, src) {
    kind = kind || null; src = kind ? (src || '') : '';
    if (kind === this.kind && src === this.src) return;
    this.kind = kind; this.src = src; this.failed = false; this.ar = 16 / 9;
    this.v.hidden = kind !== 'video'; this.img.hidden = kind !== 'image';
    if (kind === 'video') this.v.src = src; else { this.v.removeAttribute('src'); this.v.load(); }
    if (kind === 'image') this.img.src = src; else this.img.removeAttribute('src');
    this.geom(); this.paintNote();
  }
  geom() {
    const el = this.kind === 'video' ? this.v : this.kind === 'image' ? this.img : null;
    const w = el ? (el.videoWidth || el.naturalWidth) : 0, h = el ? (el.videoHeight || el.naturalHeight) : 0;
    if (w && h) { this.ar = w / h; el.style.aspectRatio = `${w} / ${h}`; }
    this.applyFrame();
  }
  /* Framing as renderer.py does it: crop fills the 9:16 frame (cover), blur fit shows the whole picture
     (contain) over a blurred copy of itself. The transform is animated, so switching frames glides. */
  applyFrame() {
    const frame = this.s ? this.s.frame : 'crop';
    const rho = (this.kind ? this.ar : 16 / 9) / (9 / 16);
    const k = frame === 'blur_fit' ? Math.min(1, rho) : Math.max(1, rho);
    (this.kind === 'image' ? this.img : this.v).style.setProperty('--k', k.toFixed(4));
    this.bgOn = !!this.kind && frame === 'blur_fit';
    this.bg.style.opacity = this.bgOn ? '1' : '0';
    this.draw(); this.watch();
  }
  draw() {
    if (!this.bgOn) return;
    const el = this.kind === 'image' ? this.img : this.v;
    if (this.kind === 'video' && el.readyState < 2) return;
    const sw = el.videoWidth || el.naturalWidth, sh = el.videoHeight || el.naturalHeight;
    if (!sw || !sh) return;
    let cw = sw, ch = sh;                             // the renderer blurs a centred 9:16 crop of the frame
    if (sw / sh > 9 / 16) cw = sh * 9 / 16; else ch = sw * 16 / 9;
    try { this.bg.getContext('2d').drawImage(el, (sw - cw) / 2, (sh - ch) / 2, cw, ch, 0, 0, this.bg.width, this.bg.height); } catch (_) {}
  }
  watch() {                                           // repaint the blurred backdrop on every presented frame
    if (!this.bgOn || this.kind !== 'video' || this.looping || !this.v.requestVideoFrameCallback) return;
    this.looping = true;
    const step = () => {
      if (this.dead || !this.bgOn || this.kind !== 'video') { this.looping = false; return; }
      this.draw(); this.v.requestVideoFrameCallback(step);
    };
    this.v.requestVideoFrameCallback(step);
  }
  paintNote() {
    const text = this.s && !this.s.captions ? 'Captions are off'
      : this.failed ? 'Preview unavailable'
      : !this.kind ? 'Find a video for real frames' : '';
    this.note.textContent = text; this.note.hidden = !text;
  }
  apply(s, st) {
    const key = `${PV.ver}|${JSON.stringify([s, st])}`;
    if (key === this.key) return;
    this.key = key; this.s = s; this.st = st;
    this.caps.style(s, st);
    const ck = JSON.stringify([s.lang, st.display, st.uppercase, st.max_words_per_line, st.max_chars_per_line, st.strip_punct,
      st.highlight_mode, st.box, st.anim, st.active_scale, st.emphasis_scale, st.word_colors, st.highlight_color]);
    if (ck !== this.caps.ck) this.caps.setModel(pvSampleModel(s.lang, st), ck);
    this.paintNote(); this.applyFrame();
    this.step(PV.tick);
    this.caps.remeasure();
  }
  step(n) {                                           // the sample phrase: one unit per tick
    const m = this.caps.m;
    if (this.dead || !m || !m.units.length) return;
    this.caps.show(n % m.units.length);
  }
}

/* A caption layer over a real video: the Edit modal and the Edits page. Its words are the clip's transcript and its
   clock is the video's own. The source's timeline is absolute, so no clip offset is added. */
class PvOverlay {
  constructor({ host, video, read, words }) {
    this.host = host; this.video = video; this.read = read; this.wordsOf = words;
    this.cap = document.createElement('div');
    this.cap.className = 'pv-cap'; this.cap.setAttribute('aria-hidden', 'true'); this.cap.hidden = true;
    host.appendChild(this.cap);
    this.caps = new PvCaps(this.cap);
    this.key = ''; this.dead = false; this.looping = false;
    this.onclock = () => this.tick(); this.onplay = () => this.play();
    ['loadeddata', 'seeked', 'timeupdate', 'pause', 'emptied'].forEach(ev => video.addEventListener(ev, this.onclock));
    video.addEventListener('play', this.onplay);
    PV.overlays.add(this);
    this.refresh();
  }
  destroy() {
    if (this.dead) return;
    this.dead = true; PV.overlays.delete(this); this.cap.remove();
    ['loadeddata', 'seeked', 'timeupdate', 'pause', 'emptied'].forEach(ev => this.video.removeEventListener(ev, this.onclock));
    this.video.removeEventListener('play', this.onplay);
  }
  /* Any control or word change (from pvApply): restyle, and rebuild the text only when its shape changed. */
  refresh() {
    if (this.dead) return;
    const r = this.read(); if (!r) return;
    const words = (this.wordsOf() || []).filter(w => String(w.t || '').trim());
    const ws = words.map(w => [w.t, w.s, w.e, w.score]);
    const s = { lang: pvIsRtl(words) ? 'ar' : 'en', captions: !!r.captions && words.length > 0, platform: r.platform };
    const st = resolveCap(r.preset, r.ov);
    const key = `${PV.ver}|${JSON.stringify([s, st, ws])}`;
    if (key === this.key) return;
    this.key = key;
    this.caps.style(s, st);
    const ck = JSON.stringify([s.lang, st.display, st.uppercase, st.max_words_per_line, st.max_chars_per_line, st.strip_punct,
      st.highlight_mode, st.box, st.anim, st.active_scale, st.emphasis_scale, st.word_colors, st.highlight_color, st.min_gap, ws]);
    if (ck !== this.caps.ck) this.caps.setModel(pvTimedModel(words, st), ck);
    this.tick();
    this.caps.remeasure();
  }
  tick() {
    const m = this.caps.m;
    if (this.dead || !m) return;
    const t = this.video.currentTime;
    let pos = -1;
    for (const ev of m.events || []) { if (t < ev.s) break; if (t < ev.e) { pos = ev.pos; break; } }
    this.caps.show(pos);
  }
  /* While the video plays, the lit word follows each presented frame. */
  play() {
    if (this.looping || this.dead) return;
    this.looping = true;
    const v = this.video;
    const frame = () => {
      if (this.dead) return;
      this.tick();
      if (v.paused || v.ended) { this.looping = false; return; }
      if (v.requestVideoFrameCallback) v.requestVideoFrameCallback(frame); else requestAnimationFrame(frame);
    };
    frame();
  }
}

function pvSync() {                                  // any change: one repaint per frame, after the page has updated
  if (!pvQueued) pvQueued = requestAnimationFrame(() => { pvQueued = 0; pvApply(); });
}
function pvLive() {
  if (PV.home && (PV.home.dead || !PV.home.root.isConnected)) { PV.home.destroy(); PV.home = null; }
  if (PV.big && (PV.big.dead || !PV.big.root.isConnected)) { PV.big.destroy(); PV.big = null; }
  PV.overlays.forEach(o => { if (!o.host.isConnected) o.destroy(); });
}
function pvApply() {
  pvLive();
  const s = pvReadState();
  if (s && (PV.home || PV.big)) {
    const st = resolveCap(s.preset, s.ov);
    [PV.home, PV.big].forEach(p => { if (p) p.apply(s, st); });
  }
  PV.overlays.forEach(o => o.refresh());
}
function pvSetMedia(kind, src) {                     // a found video, a dropped file, or a thumbnail (kind 'image')
  PV.media = { kind: kind || null, src: kind ? (src || '') : '' };
  [PV.home, PV.big].forEach(p => { if (p) p.setMedia(PV.media.kind, PV.media.src); });
  pvSync();
}
function pvMountHome() {
  pvDestroyHome();
  const root = $('#homePhone'); if (!root) return;
  PV.home = new PvPhone(root, false);
  PV.home.setMedia(PV.media.kind, PV.media.src);
  pvSync();
}
function pvDestroyHome() { if (PV.home) { PV.home.destroy(); PV.home = null; } }
function pvDetachBig() { if (PV.big) { PV.big.destroy(); PV.big = null; } }
function pvOpenBig() {
  const s = pvReadState() || { preset: 'bold-pop', frame: 'crop', lang: 'en' };
  const label = STYLES.presets?.[s.preset]?.label || s.preset;
  const m = openModal(`<div class="pv-lb">
    <div class="pv-lb-head"><div><h3>Caption preview</h3>
      <p class="hint">${esc(label)} · ${s.frame === 'blur_fit' ? 'Blur fit' : 'Center crop'} · ${s.lang === 'ar' ? 'Arabic' : 'English'}</p></div>
      <button type="button" class="icon" data-pv-act="close" aria-label="Close preview" title="Close (Esc)">${ico('x')}</button></div>
    <div class="pv-lb-stage"><div class="phone pv pv-big" id="pvBig"></div></div>
    <div class="pv-lb-foot"><span class="hint">Click the video to pause or play.</span>
      <button type="button" class="btn" data-pv-act="fs">${ico('expand')}Full screen</button></div></div>`);
  m.classList.add('pv-modal');
  PV.big = new PvPhone($('#pvBig', m), true);
  PV.big.setMedia(PV.media.kind, PV.media.src);
  pvSync();
}
document.addEventListener('click', e => {
  const b = e.target.closest?.('[data-pv-act]');
  if (!b) return;
  const act = b.dataset.pvAct;
  if (act === 'enlarge') pvOpenBig();
  else if (act === 'close') closeModal();
  else if (act === 'fs') { const p = $('#pvBig')?.requestFullscreen?.(); if (p && p.catch) p.catch(() => {}); }
});
setInterval(() => {                                  // one shared clock for the sample phrase on every phone
  pvLive();
  if (!PV.home && !PV.big) return;
  PV.tick++;
  [PV.home, PV.big].forEach(p => { if (p) p.step(PV.tick); });
}, PV_TICK_MS);

/* Customize: a control becomes an override only when the user touches it, so a preset keeps its own look. */
function custSync() {
  $$('.custwrap').forEach(w => {
    const word = $('[data-ov="display"] .on', w)?.dataset.v === 'word';
    $$('[data-word-only]', w).forEach(el => { el.hidden = !word; });
    const any = !!$('[data-touched="1"]', w);
    $$('[data-cust-foot]', w).forEach(el => { el.hidden = !any; });
  });
}
function capChanged() { custSync(); pvSync(); }

function paintStyles(root) {
  const grid = $('.styleGrid', root); if (!grid) return;
  const tab = (root.dataset && root.dataset.styleTab) || 'quick';
  const sel = $('.stylePreset', root)?.value || 'bold-pop';
  if (tab === 'my') {
    const tpls = getTpls();
    grid.innerHTML = `<div class="scard preset-card tpladd" data-tpladd="1" title="Save the current style as a template"><div class="card-preview" style="font-size:20px">＋</div><div class="card-label">Save current</div></div>`
      + (tpls.length ? tpls.map((t, i) => tplCardHTML(t, i, sel)).join('')
        : `<div class="note">No templates yet — tweak a style, then hit “Save current”.</div>`);
    return;
  }
  const entries = Object.entries(STYLES.presets || {});
  if (!entries.length) {
    grid.innerHTML = `<div class="note" style="padding:16px">Loading presets...</div>`;
    return;
  }
  grid.innerHTML = entries.map(([k, p]) => cardHTML(k, p, STYLES.base, sel)).join('');
}
function mountStyles(root, preset) {
  if ($('.stylePreset', root)) $('.stylePreset', root).value = preset || 'bold-pop';
  $$('.sampleLang button', root).forEach(x => x.classList.toggle('on', x.dataset.l === sampleLang));
  paintStyles(root);
}
function collectOverrides(root) {
  return readOpts(root).caption_style.overrides;
}
let editCtx = null;
function currentClipCtx() { return editCtx; }   // set by the Edit modal; null elsewhere
let _pv; function previewReal(root) {
  clearTimeout(_pv); _pv = setTimeout(async () => {
    if (typeof currentClipCtx !== 'function' || !currentClipCtx()) return;
    const { pid, rank, t } = currentClipCtx();
    const img = $('.capPrev', root); if (!img) return;
    try {
      const r = await fetch(`/api/projects/${pid}/clips/${rank}/caption-preview`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Marrow': '1' },
        body: JSON.stringify({ t, style: { preset: $('.stylePreset', root)?.value || 'bold-pop', overrides: collectOverrides(root) } }) });
      const d = await r.json(); img.src = d.image; img.hidden = false;
      const note = $('.capPrevNote', root); if (note) note.hidden = true;
    } catch (e) { /* keep the old preview on failure */ }
  }, 300);
}
// one global ticker lights the active word on every card (cheap, no per-card timers)
setInterval(() => {
  if (!document.querySelector('.scard')) return;   // only while a picker is visible
  tickIdx = (tickIdx + 1) % 4;
  document.querySelectorAll('.scard .cap').forEach(cap => cap.querySelectorAll('.w').forEach((w, i) => {
    if (w.classList.contains('solo')) {
      const arr = (w.dataset.words || '').split(',');
      w.textContent = arr[tickIdx % arr.length] || '';
      const pill = w.dataset.pill;
      w.style.color = pill ? w.dataset.pt : w.dataset.hl;
      w.style.transform = `scale(${(+w.dataset.sc || 115) / 100})`;
      w.style.background = pill || 'transparent';
      w.style.borderRadius = '.25em'; w.style.padding = pill ? '0 .25em' : '0';
      return;
    }
    const on = i === tickIdx, pill = w.dataset.pill;
    w.style.color = on ? (pill ? w.dataset.pt : w.dataset.hl) : '';
    w.style.transform = on ? `scale(${w.dataset.sc / 100})` : 'scale(1)';
    w.style.background = on && pill ? pill : 'transparent';
    w.style.borderRadius = '.25em'; w.style.padding = on && pill ? '0 .25em' : '0';
  }));
}, 450);
(async () => {
  try {
    const d = await (await fetch('/api/caption-styles')).json();
    if (d && d.presets && Object.keys(d.presets).length) {
      STYLES = d;
      try { injectFonts(STYLES.presets); } catch (_) {}
      repaintStyles(); pvSync();
    }
  } catch (_) { /* fallback presets already rendered */ }
})();
function repaintStyles() {
  document.querySelectorAll('.styleGrid').forEach(g => {
    const scope = g.closest('.optbody,.modal') || document;
    paintStyles(scope);
  });
}
document.addEventListener('click', e => {
  const stp = e.target.closest('[data-step]');
  if (stp) {                                     // +/- steppers (number of clips)
    const inp = stp.parentElement.querySelector('input[type="number"]');
    if (inp) {
      const lo = +inp.min || 1, hi = +inp.max || 20;
      inp.value = Math.max(lo, Math.min(hi, (+inp.value || lo) + (+stp.dataset.d)));
      inp.dispatchEvent(new Event('input', { bubbles: true }));
    }
    return;
  }
  const tdel = e.target.closest('[data-tpldel]');
  if (tdel) {
    e.stopPropagation();
    const scope = tdel.closest('.optbody,.modal,#styleCard,.edside') || document;
    const tpls = getTpls(); tpls.splice(+tdel.dataset.tpldel, 1); setTpls(tpls);
    paintStyles(scope); return;
  }
  const add = e.target.closest('[data-tpladd]');
  if (add) {
    const scope = add.closest('.optbody,.modal,#styleCard,.edside') || document;
    const name = prompt('Template name:');
    if (name && name.trim()) {
      const cur = readStyleRoot(scope);
      const tpls = getTpls();
      tpls.push({ name: name.trim().slice(0, 40), preset: cur.preset, overrides: cur.overrides });
      setTpls(tpls); paintStyles(scope); toast('Template saved', 'ok');
    }
    return;
  }
  const stb = e.target.closest('.preset-tabs button');
  if (stb) {
    const scope = stb.closest('.optbody,.modal,#styleCard,.edside') || document;
    if (scope.dataset) scope.dataset.styleTab = stb.dataset.st;
    $$('.preset-tabs button', scope).forEach(x => x.classList.toggle('on', x === stb));
    paintStyles(scope);
    return;
  }
  const car = e.target.closest('[data-car]');
  if (car) {
    const track = car.closest('.carousel')?.querySelector('.carousel-track');
    if (track) track.scrollBy({ left: 240 * (+car.dataset.car || 1), behavior: 'smooth' });
    return;
  }
  const card = e.target.closest('.styleGrid .scard');
  if (card && !card.hasAttribute('data-tpladd')) {
    const scope = card.closest('.optbody,.modal,#styleCard,.edside') || document;
    const hid = $('.stylePreset', scope); if (hid) hid.value = card.dataset.k;
    const t = (card.dataset.tpl !== undefined && card.dataset.tpl !== '') ? getTpls()[+card.dataset.tpl] : null;
    paintStyles(scope); previewReal(scope); paintPlan();
    scope.querySelectorAll('.custwrap').forEach(c => {
      c.innerHTML = customizeHTML(t ? (t.overrides || {}) : readStyleRoot(scope).overrides, card.dataset.k);
    });
    capChanged();
    return;
  }
  const lb = e.target.closest('.sampleLang button');
  if (lb) {
    sampleLang = lb.dataset.l;
    $$('.sampleLang button').forEach(x => x.classList.toggle('on', x === lb));
    repaintStyles(); capChanged();
    return;
  }
});
document.addEventListener('change', e => {
  if (e.target.closest?.('#plist .project-checkbox')) updateSelection();
  touchedChange(e.target);
});
document.addEventListener('input', e => touchedChange(e.target));
function touchedChange(el) {
  if (el.closest?.('#optbox')) paintPlan();
  if (el.dataset?.ov) el.dataset.touched = '1';
  if (el.dataset?.ovList) $$('[data-ov-list="word_colors"]', el.closest('.custwrap') || document).forEach(x => { x.dataset.touched = '1'; });
  if (el.type === 'range' && el.dataset?.ov) { const out = el.parentElement.querySelector('output'); if (out) out.textContent = el.value + (el.dataset.unit || ''); }
  if (el.type === 'range' && el.dataset?.opt) { const out = el.closest('.opt-group')?.querySelector('output'); if (out) out.textContent = el.value + (el.dataset.unit || ''); }
  if (el.dataset?.ov || (el.dataset?.opt && el.closest('.optbody,.modal')?.querySelector('.styleGrid'))) {
    const scope = el.closest('.optbody,.modal,#styleCard'); if (scope) previewReal(scope);
  }
  if (el.closest?.('.modal,.edside,#ed-words,#edx-words')) pvSync();
  if (el.closest?.('#styleCard,#optbox,.custwrap')) capChanged();
}
/* Clip cards: hover to preview (muted), rewind when the pointer leaves. */
document.addEventListener('pointerover', e => {
  const box = e.target.closest?.('.clip .vid'); const v = box?.querySelector('video');
  if (v && v.paused && !e.target.closest('.expand')) v.play().catch(() => {});
});
document.addEventListener('pointerout', e => {
  const box = e.target.closest?.('.clip .vid');
  if (!box || (e.relatedTarget && box.contains(e.relatedTarget))) return;
  const v = box.querySelector('video');
  if (v && !v.paused) { v.pause(); try { v.currentTime = 0; } catch (_) {} }
});

/* ---------- sidebar / engine ---------- */
function renderSide() {
  const r = state.route?.name;
  $$('#nav a').forEach(a => a.classList.toggle('on', a.dataset.r === r || (r === 'project' && a.dataset.r === 'projects')));
  const n = state.projects.filter(p => ACTIVE.has(p.status)).length;
  const c = $('#navcount'); c.hidden = !n; c.textContent = n;
  const s = state.system;
  const row = (tone, t) => `<div class="dotrow"><span class="dot ${tone}"></span><span>${t}</span></div>`;
  let html = '<h4>Engine</h4>';
  if (!s) html += row('', 'Checking…');
  else {
    html += row(s.ffmpeg ? 'ok' : 'bad', s.ffmpeg ? 'FFmpeg ready' : 'FFmpeg missing');
    html += s.gpu ? row('ok', 'Whisper on GPU')
      : row('warn', `Whisper on CPU${s.gpu_error ? `<br><span class="muted">${esc(String(s.gpu_error).slice(0, 80))}</span>` : ''}`);
    html += row(s.encoder === 'h264_nvenc' ? 'ok' : '', s.encoder === 'h264_nvenc' ? 'Encoder: NVENC' : 'Encoder: libx264');
    html += s.ollama.reachable && s.ollama.model_ready ? row('ok', 'AI scoring ready')
      : row(s.ollama.reachable ? 'warn' : '', s.ollama.reachable ? 'AI model not pulled' : 'AI scoring off (heuristics)');
  }
  $('#engine').innerHTML = html;
}
async function refreshSystem(fresh) { try { state.system = await api('/api/system' + (fresh ? '?fresh=1' : '')); } catch (_) {} renderSide(); }

/* ---------- project card (home + projects) ---------- */
/* ---------- project card (home + projects) ---------- */
function projectCard(p, manage) {
  const running = ACTIVE.has(p.status);
  const eng = p.engine?.transcribe ? ` · ${p.engine.transcribe.device === 'cuda' ? 'GPU' : 'CPU'}` : '';
  const meta = p.status === 'done' ? `${p.clips.length} clip${p.clips.length === 1 ? '' : 's'} · ${platLabel(p.settings.platform)}${eng}`
    : p.status === 'error' ? 'Failed' : p.stage;
  const label = p.status === 'done' ? 'Ready' : p.status[0].toUpperCase() + p.status.slice(1);
  const link = `<a class="pc-link" href="#/p/${p.id}">
      <div class="pthumb">${p.thumb ? `<img src="${p.thumb}" alt="" loading="lazy">` : `<span class="ph">${ico(p.status === 'error' ? 'alert' : running ? 'refresh' : 'film')}</span>`}
        <span class="pill ${p.status}"><i class="pd"></i>${label}</span>
        ${running ? `<div class="pbar"><i style="width:${Math.round((p.progress || 0) * 100)}%"></i></div>` : ''}</div>
      <div class="pbody"><h4 dir="auto">${esc(p.name)}</h4><div class="m">${esc(meta)} · ${fmtDate(p.created)}</div></div></a>`;
  if (!manage) return `<div class="project-card">${link}</div>`;
  return `<div class="project-card ${p.locked ? 'locked' : ''}" data-id="${p.id}">
    <div class="pc-top">
      <label class="check" title="Select project"><input type="checkbox" class="project-checkbox" data-id="${p.id}" aria-label="Select ${esc(p.name)}"><span></span></label>
      <button class="icon sm" data-act="lock-proj" data-id="${p.id}" title="${p.locked ? 'Unlock project' : 'Lock project'}" aria-label="${p.locked ? 'Unlock' : 'Lock'} project">${ico(p.locked ? 'lock' : 'unlock')}</button>
    </div>${link}</div>`;
}
const projSig = list => JSON.stringify(list.map(p => [p.id, p.status, p.stage, p.progress, p.name, p.thumb, p.clips.length, !!p.locked]));

/* ---------- views ---------- */
const main = $('#main');

const Home = { probeId: null, timer: null, probeReady: false, probeFailed: false, info: null, url: '', objUrl: null,
  last: null, done: false, infoReady: false, readyShown: false, localName: null };
const FOUND_KEY = 'marrowFound';   // the fetched link + probe id, kept for the tab so a reload or a page switch doesn't refetch
const LINK_RE = /^https?:\/\/[^\s/]+\.[^\s]+/i;
function viewHome() {
  if (!state.opts) state.opts = state.settings ? state.settings.job_defaults : { clips: 5, duration: 45, platform: 'shorts', layout: 'crop', captions: true, use_llm: true, zoom: false, caption_style: { preset: 'bold-pop', overrides: {} } };
  const s = state.system;
  pvDestroyHome();
  main.innerHTML = `
  ${s && !s.ffmpeg ? `<div class="banner bad">${ico('alert')}<div>FFmpeg wasn’t found, so clips can’t be rendered. Install it (Windows: <code>winget install ffmpeg</code>), open a new terminal and restart Marrow.</div></div>` : ''}
  <header class="page-head">
    <div>
      <div class="eyebrow">Local AI video clipping</div>
      <h1 class="page-title">One long video. Many viral clips.</h1>
      <p class="page-sub">Paste a link or drop a file. Marrow finds the strongest moments and renders captioned Shorts and Reels, all on your machine.</p>
    </div>
    <ol class="steps" aria-label="How Marrow works"><li><b>1</b>Find</li><li><b>2</b>Transcribe</li><li><b>3</b>Score</li><li><b>4</b>Render</li></ol>
  </header>
  <div class="home">
    <div class="home-main">
      <section class="card" id="sourceCard">
        <div class="source-grid">
          <div class="source-col">
            <label class="label" for="url">Paste a link</label>
            <div class="urlrow">
              <input type="text" id="url" placeholder="https://youtube.com/watch?v=…" value="${esc(state.url)}" autocomplete="off" spellcheck="false">
              <button class="btn primary" id="findBtn">Find video</button>
            </div>
            <p class="hint">YouTube, Vimeo, X and most sites that yt-dlp supports.</p>
          </div>
          <div class="source-col">
            <span class="label">Or upload a file</span>
            <div class="dropzone" id="dropbox"><div id="uprow"></div></div>
            <div class="upbar" id="upbar" hidden><i></i></div>
          </div>
        </div>
        <div id="foundWrap"></div>
      </section>
      <section class="card" id="styleCard">
        <div class="card-head"><div><h3>Caption style</h3><p class="hint">Pick a look. Previews use your real frames once a video is found.</p></div></div>
        ${styleSectionHTML(state.opts?.caption_style?.preset || 'bold-pop')}
        <details class="cust"><summary>Customize style</summary><div id="homeCustomize" class="custwrap"></div></details>
      </section>
      <div class="sechead"><h2>Recent projects</h2>${state.projects.length ? '<a class="btn ghost sm" href="#/projects">View all</a>' : ''}</div>
      <div id="recent"></div>
    </div>
    <aside class="card home-side" aria-label="Clip settings">
      <div class="card-head"><h3>Clip settings</h3></div>
      <div id="optbox">${optsPanel(state.opts, true)}</div>
      <div class="plan" id="planBox"></div>
      <div class="cta">
        <button class="btn primary lg block" id="genBtn" disabled>Generate clips</button>
        <p class="hint" id="genNote"></p>
      </div>
    </aside>
  </div>`;
  paintUploadRow(); paintRecent();
  $('#homeCustomize').innerHTML = customizeHTML(state.opts?.caption_style?.overrides, state.opts?.caption_style?.preset);
  $$('details.cust').forEach(d => { d.open = custOpen; });
  mountStyles($('#styleCard'), state.opts?.caption_style?.preset || 'bold-pop');
  custSync(); pvMountHome();
  setGenBtn();
  paintPlan();
  $('#findBtn').onclick = () => findVideo(($('#url')?.value || '').trim());
  const urlIn = $('#url');
  urlIn.addEventListener('input', e => onUrlTyped(e.target.value));
  urlIn.addEventListener('paste', () => { setTimeout(() => autoFind(urlIn.value), 0); });   // a pasted link is fetched at once
  urlIn.addEventListener('keydown', e => { if (e.key === 'Enter') findVideo(e.target.value.trim()); });
  $('#genBtn').onclick = startProject;
  const box = $('#dropbox');
  ['dragenter', 'dragover'].forEach(ev => box.addEventListener(ev, e => { e.preventDefault(); box.classList.add('drag'); }));
  ['dragleave', 'drop'].forEach(ev => box.addEventListener(ev, e => { e.preventDefault(); box.classList.remove('drag'); }));
  restoreFound();
}
function setGenBtn() {
  const pend = state.pending;
  const hasUrl = !!(Home.url || '').trim();
  const ok = !!(pend && pend.upload) || Home.infoReady || Home.probeReady || (Home.probeFailed && hasUrl && !pend);
  const b = $('#genBtn'); if (b) b.disabled = !ok;
  const n = $('#genNote'); if (!n) return;
  n.textContent = !ok ? 'Find a video or upload one to unlock generation.'
    : (Home.probeFailed && !Home.probeReady && !pend) ? 'No preview, but Marrow can still fetch the full video when you generate.'
    : (Home.infoReady && !Home.probeReady && !pend) ? 'Ready. The preview is still loading, but generating doesn’t need it.'
    : 'Ready. Adjust the settings, then generate.';
}
function resetFound() {
  stopPolling();
  Object.assign(Home, { probeId: null, probeReady: false, probeFailed: false, info: null, url: '',
    last: null, done: false, infoReady: false, readyShown: false });
  const w = $('#foundWrap'); if (w) w.innerHTML = '';
  saveFound(); setGenBtn(); pvSetMedia(null);
}
function saveFound() {
  try {
    if (Home.probeId && Home.url) sessionStorage.setItem(FOUND_KEY, JSON.stringify({ url: Home.url, probeId: Home.probeId }));
    else sessionStorage.removeItem(FOUND_KEY);
  } catch (_) {}
}
function loadFound() {
  try { return JSON.parse(sessionStorage.getItem(FOUND_KEY) || 'null'); } catch (_) { return null; }
}
function onUrlTyped(v) {
  state.url = v;
  if (v) clearPending();                                   // typing a link replaces a dropped file
  if ((v || '').trim() !== Home.url) resetFound();         // a different link: drop the old card
}
// A pasted link is fetched straight away. Typed text waits for Enter or Find, so half-typed links aren't fetched.
function autoFind(t) {
  t = (t || '').trim();
  if (LINK_RE.test(t)) findVideo(t);
}
function startPolling() {
  if (Home.timer || !Home.probeId || Home.done) return;
  Home.timer = setInterval(pollProbe, 800);
  pollProbe();
}
function stopPolling() { clearInterval(Home.timer); Home.timer = null; }
// Repaint the fetched video after a page switch (or a reload) instead of asking the user to fetch it again.
function restoreFound() {
  if (Home.localName && Home.objUrl) { paintLocalCard(); return; }
  if (!Home.probeId) { setGenBtn(); return; }
  if (Home.last) paintProbe(Home.last); else setFoundState('fetching');
  setGenBtn();
  startPolling();
}
async function findVideo(url) {
  if (!url) { toast('Paste a video link first.', 'bad'); return; }
  if (Home.url === url && !Home.probeFailed) { startPolling(); return; }   // already fetched, or fetching now
  clearPending(); resetFound();
  Home.url = url; state.url = url;
  setFoundState('fetching');
  try {
    const r = await api('/api/probe', { method: 'POST', body: { url } });
    if (Home.url !== url) return;                  // the link was changed while we waited
    Home.probeId = r.id; saveFound(); startPolling();
  } catch (e) { if (Home.url === url) setFoundState('error', e.message); }
}
async function pollProbe() {
  const id = Home.probeId; if (!id) return;
  let p;
  try { p = await (await fetch('/api/probe/' + id)).json(); } catch (_) { return; }
  if (Home.probeId !== id) return;
  if (!p.state) {                                  // the server no longer knows this fetch (restart or expiry)
    stopPolling(); Home.probeId = null; Home.last = null; saveFound();
    setFoundState('error', 'The fetch expired. Press Find video again.');
    return;
  }
  Home.last = p;
  if (p.info) Home.info = p.info;
  Home.infoReady = !!p.info && p.state !== 'error' && p.state !== 'cancelled';
  Home.probeReady = p.state === 'ready';
  paintProbe(p);
  if (p.state === 'ready' || p.state === 'error' || p.state === 'cancelled') { Home.done = true; stopPolling(); }
  setGenBtn();
}
// Paints the found card for a probe payload. Only (re)builds the card when it isn't on screen,
// so the preview video isn't reloaded on every poll.
function paintProbe(p) {
  const w = $('#foundWrap'); if (!w) return;
  if (p.state === 'error' && !p.info) { setFoundState('error', p.error); return; }
  if (!p.info) { if (!w.querySelector('.found-skel')) setFoundState('fetching'); return; }
  if (!w.querySelector('#foundMedia')) { Home.readyShown = false; paintFoundCard(p); }
  if (p.state === 'ready') {
    if (!Home.readyShown) { Home.readyShown = true; setFoundReady(p); }
  } else if (p.state !== 'error') {
    const el = $('#foundProg');
    if (el) el.textContent = p.state === 'preview' ? `Preparing preview · ${Math.round((p.progress || 0) * 100)}%` : 'Preparing preview…';
  }
  if (p.state === 'error') setFoundState('error', p.error);
}
function friendlyProbeError(msg) {
  const m = String(msg || '');
  if (/sign in to confirm|not a bot|\bbot\b/i.test(m))
    return { title: 'YouTube asked for a sign-in check', body: 'Marrow tried every YouTube client. Sign in to YouTube in Firefox or Chromium (or in Chrome or Edge with that browser closed), then pick it under Settings → YouTube cookies (optional, only needed when YouTube blocks downloads). If it still fails, run: pip install -U "yt-dlp[default,deno]".', warn: true, settings: true };
  if (/403|forbidden/i.test(m))
    return { title: 'YouTube refused the preview (403)', body: 'Pick a browser you are signed in to (Firefox or Chromium work well) under Settings → YouTube cookies (optional), and run: pip install -U "yt-dlp[default,deno]". You can still generate: Marrow retries with other clients.', warn: true, settings: true };
  if (/private|unavailable|deleted|region|geo|404|not found/i.test(m))
    return { title: 'Video unavailable', body: 'This video can’t be accessed. It may be private, deleted, or blocked in your region.', warn: true };
  if (/no playable preview|not written/i.test(m))
    return { title: 'No preview stream', body: 'The site didn’t offer a playable preview. The full download may still work, so you can try generating anyway.', warn: true };
  const first = m.split('\n')[0].replace(/^[A-Za-z]*Error:\s*/, '').replace(/^ERROR:\s*/i, '').slice(0, 220);
  return { title: 'Couldn’t fetch this video', body: first || 'Please try another link.', warn: false };
}
function setFoundState(st, msg) {
  const w = $('#foundWrap'); if (!w) return;
  if (st === 'fetching') {
    Home.probeFailed = false;
    w.innerHTML = `<div class="found found-skel"><div class="found-media skel"><span class="chip found-chip">${ico('refresh')}Reading video…</span></div>
      <div class="found-meta"><div class="skel-line"></div><div class="skel-line short"></div><p class="hint">Fetching the title, thumbnail and a 480p preview.</p></div></div>`;
  } else if (st === 'error') {
    const f = friendlyProbeError(msg);
    Home.probeFailed = !!Home.url;
    const actions = `${f.settings ? '<button class="btn sm" data-act="go-settings">Open settings</button>' : ''}${Home.url ? '<button class="btn sm primary" data-act="generate-anyway">Try generating anyway</button>' : ''}`;
    const banner = `<div class="banner ${f.warn ? 'warn' : 'bad'}">${ico('alert')}<div><b>${esc(f.title)}</b><div class="bmsg">${esc(f.body)}</div>${actions ? `<div class="bactions">${actions}</div>` : ''}</div></div>`;
    const note = $('#foundNote');
    if (note) note.innerHTML = banner; else w.innerHTML = banner;
  }
  setGenBtn();
}
function fmtDur(sec) { return sec == null ? '–' : fmtT(sec); }
function paintFoundCard(p) {
  const w = $('#foundWrap'); if (!w) return;
  const i = p.info || {};
  const prog = p.state === 'preview' ? `Preparing preview · ${Math.round((p.progress || 0) * 100)}%` : 'Preparing preview…';
  w.innerHTML = `<div class="found">
    <div class="found-media" id="foundMedia">${p.thumb ? `<img src="${esc(p.thumb)}" alt="">` : '<div class="skel"></div>'}<span class="chip found-chip">${ico('check')}Video found</span></div>
    <div class="found-meta">
      <h3 class="found-title" dir="auto">${esc(i.title || 'Untitled')}</h3>
      <div class="cmeta">${i.channel ? esc(i.channel) + ' · ' : ''}${i.duration != null ? fmtT(i.duration) : 'length known after download'}</div>
      <div class="found-prog" id="foundProg">${prog}</div>
      <div id="foundNote"></div>
      <div class="found-actions"><button class="btn ghost sm" data-act="clear-source">${ico('x')}Remove</button></div>
    </div></div>`;
  if (p.thumb && PV.media.kind !== 'video') pvSetMedia('image', p.thumb);
}
function setFoundReady(p) {
  Home.probeReady = true;
  const media = $('#foundMedia');
  if (media && p.preview) media.innerHTML = `<video src="${p.preview}" controls muted playsinline preload="metadata"></video><span class="chip found-chip">${ico('check')}Preview ready</span>`;
  const prog = $('#foundProg'); if (prog) prog.textContent = 'Preview ready. Generating uses the full-quality download.';
  if (p.preview) pvSetMedia('video', p.preview);
  setGenBtn();
}
function paintUploadRow() {
  const row = $('#uprow'); if (!row) return;
  const p = state.pending;
  if (p) {
    row.innerHTML = `<div class="filechip">${ico('film')}<b>${esc(p.name)}</b><span class="muted">${p.upload ? 'Uploaded' : Math.round((state.uploadPct || 0) * 100) + '%'}</span><button class="icon sm" data-act="rm-upload" title="Remove" aria-label="Remove file">${ico('x')}</button></div>`;
  } else {
    row.innerHTML = `<div class="dz-empty">${ico('upload')}<b>Drop a video here</b><span class="hint">mp4, mov, mkv, webm</span><button class="btn sm" id="fileBtn" type="button">Choose file</button><input type="file" id="file" accept="video/*,.mkv" hidden></div>`;
    const fBtn = $('#fileBtn', row); if (fBtn) fBtn.onclick = () => $('#file', row)?.click();
    const f = $('#file', row); if (f) f.onchange = () => { if (f.files[0]) handleFile(f.files[0]); };
  }
  const bar = $('#upbar'); if (bar) { bar.hidden = !(p && !p.upload); $('i', bar).style.width = Math.round((state.uploadPct || 0) * 100) + '%'; }
  setGenBtn();
}
function clearPending() {
  if (state.pending) { state.pending = null; state.uploadPct = null; paintUploadRow(); }
  if (Home.objUrl) {
    if (PV.media.kind === 'video' && PV.media.src === Home.objUrl) pvSetMedia(null);
    URL.revokeObjectURL(Home.objUrl); Home.objUrl = null;
  }
  Home.localName = null;
}
function paintRecent() {
  const r = $('#recent'); if (!r) return;
  const list = state.projects.slice(0, 6);
  const sig = projSig(list); if (r.dataset.sig === sig) return; r.dataset.sig = sig;
  r.innerHTML = list.length ? `<div class="pgrid compact">${list.map(p => projectCard(p, false)).join('')}</div>`
    : `<div class="empty">${ico('film')}<div><b>No projects yet</b><span class="hint">Paste a link above or drop a video to make your first clips.</span></div></div>`;
}
function paintLocalCard() {
  const w = $('#foundWrap'); if (!w || !Home.objUrl) return;
  const dur = Home.info?.duration;
  w.innerHTML = `<div class="found">
    <div class="found-media" id="foundMedia"><video src="${Home.objUrl}" controls muted playsinline preload="metadata"></video><span class="chip found-chip">${ico('check')}Local file</span></div>
    <div class="found-meta">
      <h3 class="found-title" dir="auto">${esc(Home.localName)}</h3>
      <div class="cmeta" id="up-meta">${dur ? `Local file · ${fmtT(dur)}` : 'Reading duration…'}</div>
      <div class="found-prog">Uploads are used directly, so nothing is downloaded.</div>
      <div class="found-actions"><button class="btn ghost sm" data-act="clear-source">${ico('x')}Remove</button></div>
    </div></div>`;
  pvSetMedia('video', Home.objUrl);
}
function handleFile(file) {
  if (!/\.(mp4|mov|mkv|webm|avi|m4v)$/i.test(file.name)) { toast('Unsupported file type. Use mp4, mov, mkv, webm, avi or m4v.', 'bad'); return; }
  state.url = ''; const u = $('#url'); if (u) u.value = '';
  resetFound();
  if (Home.objUrl) URL.revokeObjectURL(Home.objUrl);
  Home.objUrl = URL.createObjectURL(file);
  Home.localName = file.name;
  Home.info = { title: file.name, duration: null };
  paintLocalCard();
  const probe = document.createElement('video'); probe.preload = 'metadata'; probe.src = Home.objUrl;
  probe.onloadedmetadata = () => {
    Home.info = { title: file.name, duration: probe.duration };
    const mm = $('#up-meta'); if (mm) mm.textContent = `Local file · ${fmtT(probe.duration)}`;
  };
  state.pending = { name: file.name, upload: null }; state.uploadPct = 0; paintUploadRow();
  const xhr = new XMLHttpRequest();
  xhr.open('POST', '/api/upload?filename=' + encodeURIComponent(file.name));
  xhr.setRequestHeader('X-Marrow', '1');
  xhr.upload.onprogress = e => { if (e.lengthComputable) { state.uploadPct = e.loaded / e.total; paintUploadRow(); } };
  xhr.onload = () => {
    let d = {}; try { d = JSON.parse(xhr.responseText); } catch (_) {}
    if (xhr.status < 300 && d.upload) { state.pending = { name: file.name, upload: d.upload }; paintUploadRow(); toast('Upload complete. Press “Generate clips”.', 'ok'); }
    else { state.pending = null; paintUploadRow(); toast(d.error || 'Upload failed', 'bad'); }
  };
  xhr.onerror = () => { state.pending = null; paintUploadRow(); toast('Upload failed (connection lost).', 'bad'); };
  xhr.send(file);
}
function readHomeOpts() {
  const o = readOpts($('#optbox'));
  o.caption_style = readStyleRoot($('#styleCard'));
  return o;
}
async function startProject() {
  const pend = state.pending;
  if (window.Notification && Notification.permission === 'default') {
    try { Notification.requestPermission(); } catch (_) {}
  }
  if (pend && !pend.upload) { toast('Wait for the upload to finish.'); return; }
  const useUrl = !pend && Home.probeFailed && !!Home.url;
  if (!pend && !useUrl && !Home.probeId) { toast('Find a video or upload a file first.', 'bad'); return; }
  if (!pend && !useUrl && !Home.infoReady && !Home.probeReady) { toast('Still reading the video. It will be ready in a moment.'); return; }
  const settings = readHomeOpts(); state.opts = settings;
  const btn = $('#genBtn'); if (btn) btn.disabled = true;
  try {
    const body = pend ? { upload: pend.upload, settings } : useUrl ? { url: Home.url, settings } : { probe_id: Home.probeId, settings };
    const p = await api('/api/projects', { method: 'POST', body });
    state.url = ''; clearPending(); resetFound(); state.projects.unshift(p);
    location.hash = '#/p/' + p.id;
  } catch (e) { toast(e.message, 'bad'); setGenBtn(); }
}

function viewProjects() {
  main.innerHTML = `<header class="page-head">
      <div><div class="eyebrow">Library</div><h1 class="page-title">Projects</h1><p class="page-sub">Every video you’ve processed, with its clips. Lock a project to keep it out of bulk deletes.</p></div>
      <div class="head-actions"><div class="search-wrap">${ico('search')}<input class="search" id="search" placeholder="Search projects…" aria-label="Search projects"></div></div>
    </header>
    <div class="bulkbar card">
      <label class="check-row"><span class="check"><input type="checkbox" id="select-all" aria-label="Select all"><span></span></span><b>Select all</b></label>
      <span class="hint" id="sel-count"></span>
      <button id="delete-selected" class="btn danger sm" hidden></button>
    </div>
    <div id="plist"></div>`;
  $('#search').addEventListener('input', paintProjects);
  $('#select-all').addEventListener('change', toggleSelectAll);
  $('#delete-selected').addEventListener('click', deleteSelected);
  paintProjects();
}
const selectedProjects = new Set();
function updateDeleteButton() {
  const btn = $('#delete-selected'); if (!btn) return;
  const n = selectedProjects.size;
  btn.hidden = n === 0;
  btn.innerHTML = `${ico('trash')}Delete ${n} selected`;
  const c = $('#sel-count'); if (c) c.textContent = n ? `${n} selected` : '';
}
function toggleSelectAll() {
  const on = $('#select-all')?.checked;
  $$('#plist .project-checkbox').forEach(cb => {
    if (cb.closest('.project-card')?.classList.contains('locked')) return;
    cb.checked = !!on;
    const id = cb.dataset.id;
    if (on) selectedProjects.add(id); else selectedProjects.delete(id);
  });
  updateDeleteButton();
}
function updateSelection() {
  selectedProjects.clear();
  $$('#plist .project-checkbox:checked').forEach(cb => selectedProjects.add(cb.dataset.id));
  const all = $$('#plist .project-checkbox').filter(cb => !cb.closest('.project-card')?.classList.contains('locked'));
  const sa = $('#select-all');
  if (sa) sa.checked = all.length > 0 && all.every(cb => cb.checked);
  updateDeleteButton();
}
async function toggleLock(pid) {
  try {
    const p = await api(`/api/projects/${pid}/lock`, { method: 'POST', body: {} });
    mergeProject(p); paintProjects();
    toast(p.locked ? 'Project locked' : 'Project unlocked', 'ok');
  } catch (e) { toast(e.message, 'bad'); }
}
async function deleteSelected() {
  const ids = [...selectedProjects].filter(id => {
    const p = state.projects.find(x => x.id === id);
    return p && !p.locked;
  });
  if (!ids.length) { toast('Nothing to delete.', 'info'); return; }
  const r = await confirmBox({ title: `Delete ${ids.length} project${ids.length === 1 ? '' : 's'}?`, text: 'Exports will be removed from disk. Locked projects are skipped.', ok: 'Delete', danger: true });
  if (!r.ok) return;
  let n = 0;
  for (const id of ids) {
    try { await api(`/api/projects/${id}?purge=0`, { method: 'DELETE' }); n++; }
    catch (e) { toast(e.message, 'bad'); }
  }
  state.projects = state.projects.filter(x => !ids.includes(x.id));
  selectedProjects.clear();
  paintProjects();
  toast(n ? `Deleted ${n} project${n === 1 ? '' : 's'}` : 'Nothing deleted', n ? 'ok' : 'info');
}
function paintProjects() {
  const box = $('#plist'); if (!box) return;
  const q = ($('#search')?.value || '').toLowerCase();
  const list = state.projects.filter(p => p.name.toLowerCase().includes(q) || (p.source || '').toLowerCase().includes(q));
  const sig = projSig(list) + q; if (box.dataset.sig === sig) return; box.dataset.sig = sig;
  box.innerHTML = list.length ? `<div class="pgrid">${list.map(p => projectCard(p, true)).join('')}</div>` :
    `<div class="empty">${state.projects.length ? 'No projects match your search.' : 'No projects yet. Go to Home and paste a link.'}</div>`;
  $$('#plist .project-checkbox').forEach(cb => { cb.checked = selectedProjects.has(cb.dataset.id); });
  updateSelection();
}

/* ----- project page ----- */
function friendlyError(err) {
  const e = err || '';
  if (/not a bot|sign in to confirm|sign in to youtube/i.test(e)) return ['YouTube asked for a sign-in check',
    'Marrow tried every YouTube client it has, and YouTube still wants a signed-in browser session.',
    'Update yt-dlp (pip install -U "yt-dlp[default,deno]"), then optionally open Settings → YouTube cookies, sign in to YouTube in Firefox or Chromium (or another browser) and pick it. Press Retry.'];
  if (/403|Forbidden/i.test(e)) return ['YouTube refused the request (403)',
    'Every player client was refused with 403 Forbidden.',
    'Update yt-dlp, optionally set YouTube cookies under Settings → YouTube cookies, then press Retry. If it keeps failing, try again later or from another network.'];
  if (/Live streams?/i.test(e)) return ['Live stream', 'Live streams are not supported.',
    'Wait for the stream to end and become a regular video.'];
  if (/Private|unavailable|404|not found|region|geo-block/i.test(e)) return ['Video unavailable', 'This video cannot be accessed.',
    'It may be private, deleted, or region-blocked.'];
  return ['Something went wrong', 'The job failed.', ''];
}
const _eta = { l: '', st: '' };
function etaInfo(p) {
  const pct = Math.round((p.progress || 0) * 100);
  const st = p.stage || '';
  let left = (p.eta_sec != null && p.eta_at) ? Math.max(0, p.eta_sec - (Date.now() / 1000 - p.eta_at)) : null;
  if (st !== _eta.st) _eta.st = st;
  else if (left != null && _eta.l !== '' && left > (+_eta.l) * 1.1) left = +_eta.l;
  _eta.l = left == null ? '' : left;
  const leftTxt = left == null ? ((/transcrib/i.test(st) && pct < 15) ? 'calculating…' : '') : (left < 5 ? 'finishing…' : `~${fmtT(left)} left`);
  const el = p.started ? `elapsed ${fmtT(Date.now() / 1000 - p.started)}` : '';
  return { pct, st, leftTxt, el };
}
function curProject() { return state.projects.find(p => p.id === state.route.id); }
function viewProject() {
  const p = curProject();
  if (!p) { main.innerHTML = `<div class="empty big">${ico('alert')}<div><b>Project not found</b><span class="hint">It may have been deleted.</span></div><a class="btn sm" href="#/projects">Back to projects</a></div>`; return; }
  main.innerHTML = `<header class="phead">
      <a class="icon back" href="#/projects" aria-label="Back to projects" title="Back">${ico('back')}</a>
      <div class="ptitle"><h2 id="pname" dir="auto"></h2><span class="pill" id="pstate"></span><button class="icon sm" data-act="rename" title="Rename project" aria-label="Rename project">${ico('pen')}</button></div>
      <div class="actions" id="pactions"></div>
    </header>
    <div class="pmeta" id="pmeta"></div>
    <section class="card pprog" id="pprog" hidden>
      <div class="pprog-top">
        <div class="pct" id="pp-pct">0%</div>
        <div class="pprog-info"><b id="pp-stage">Starting</b><span id="pp-sub"></span></div>
        <div class="pprog-end"><span class="chip" id="pp-el"></span><span class="chip" id="pp-left"></span></div>
      </div>
      <div class="bar"><i id="pp-fill"></i></div>
      <ol class="steps-run" id="pp-steps" aria-label="Progress steps"></ol>
    </section>
    <div id="pstatus"></div>
    <div class="dash" id="dash">
      <section class="card scan" id="scan" data-state="idle" hidden>
        <header class="scan-head"><span class="scan-title">${ico('sparkle')}<b>Live analysis</b></span><span class="pill" id="scanPill">Idle</span></header>
        <div class="scan-stage">
          <video id="scanVideo" muted playsinline preload="auto"></video>
          <div class="scan-grid"></div><div class="scan-sweep"></div>
          <div class="scan-top"><span class="scan-chip label" id="scanLabel">Scanning content</span><span class="scan-chip live"><i></i>Live</span></div>
          <div class="scan-bottom">
            <div class="scan-lines mono"><div>&gt; thread <b id="thr">active</b></div><div>&gt; audio <b id="trs">processing</b></div></div>
            <button class="scan-play" id="scanPlay" type="button" title="Pause preview" aria-label="Pause preview">${ico('pause', 'fill')}</button>
          </div>
          <p class="scan-note" id="scanNote" hidden></p>
        </div>
        <div id="hw-slot"></div>
        <div class="strip" id="strip" hidden><img id="stripImg" alt=""><div class="marks" id="marks"></div><div class="head" id="playhead"></div></div>
        <details class="logs"><summary>System log</summary><div class="logbody" id="logbody"></div></details>
      </section>
      <section class="clips-col">
        <div class="sechead flush">
          <h2>Clips</h2>
          <div class="head-actions"><span class="chip" id="clipCount"></span><button class="btn ghost sm" id="scanToggle" data-act="toggle-analysis" hidden></button></div>
        </div>
        <div class="clips" id="clipgrid"></div>
      </section>
    </div>`;
  Scan.reset();
  paintProject(p, true);
  const sp = $('#scanPlay');
  if (sp) sp.onclick = () => {
    const v = $('#scanVideo'); if (!v) return;
    if (v.paused) v.play().catch(() => {}); else v.pause();
    paintScanPlay();
  };
  if (ACTIVE.has(p.status)) { Scan.mount(p.id); hwStart(); refreshProject(p.id); }
}
const STEP_NAMES = ['Fetch', 'Transcribe', 'Score', 'Render'];
function stepIndex(stage, status) {
  if (status === 'done') return 4;
  const s = (stage || '').toLowerCase();
  if (/render|smart layout|clip \d/.test(s)) return 3;
  if (/analy|scor|rank|shortlist|candidate|llm/.test(s)) return 2;
  if (/transcrib|audio|extract/.test(s)) return 1;
  return 0;
}
function paintSteps(active) {
  const box = $('#pp-steps'); if (!box || box.dataset.sig === String(active)) return;
  box.dataset.sig = String(active);
  box.innerHTML = STEP_NAMES.map((n, i) => `<li class="step ${i < active ? 'done' : i === active ? 'active' : ''}"><span class="sdot">${i < active ? ico('check') : i + 1}</span>${n}</li>`).join('');
}
function paintProject(p, force) {
  $('#pname').textContent = p.name;
  const pst = $('#pstate');
  if (pst) { pst.className = 'pill ' + p.status; pst.innerHTML = `<i class="pd"></i>${p.status === 'done' ? 'Ready' : p.status[0].toUpperCase() + p.status.slice(1)}`; }
  const src = p.source_kind === 'url' ? `<a href="${esc(p.source)}" target="_blank" rel="noopener">Original link ${ico('external')}</a>` : `<span>${p.source_kind === 'upload' ? 'Uploaded file' : 'Local file'}</span>`;
  const eng = p.engine?.transcribe ? `<span>Whisper ${p.engine.transcribe.device === 'cuda' ? 'GPU' : 'CPU'} · ${esc(p.engine.transcribe.model || '')}</span>` : '';
  $('#pmeta').innerHTML = `<span>${platLabel(p.settings.platform)}</span><span>${fmtDate(p.created)}</span>${eng}${src}`;
  const asig = p.status + ':' + p.clips.length + ':' + (p.locked ? 1 : 0);
  const act = $('#pactions');
  if (force || act.dataset.sig !== asig) {
    act.dataset.sig = asig;
    const del = `<button class="icon danger" data-act="del-project" title="Delete project" aria-label="Delete project">${ico('trash')}</button>`;
    act.innerHTML = ACTIVE.has(p.status)
      ? `<button class="btn danger" data-act="cancel">${ico('x')}Cancel</button>`
      : p.status === 'done'
        ? `<button class="btn" data-act="regen">${ico('refresh')}Regenerate</button>${p.clips.length ? `<button class="btn primary" data-act="export-all">${ico('download')}Download all</button>` : ''}<button class="btn ghost" data-act="open-folder">${ico('folder')}Open folder</button>${del}`
        : `<button class="btn primary" data-act="regen">${ico('refresh')}Try again</button>${del}`;
  }
  const running = ACTIVE.has(p.status);
  const queued = p.status === 'queued';
  const scan = $('#scan'), ps = $('#pstatus'), dash = $('#dash');
  if (p.status === 'error') {
    const [et, em, eh] = friendlyError(p.error);
    ps.innerHTML = `<div class="status err">${ico('alert')}<div class="status-body"><b>${esc(et)}</b><p>${esc(em)}</p>${eh ? `<p class="hint">${esc(eh)}</p>` : ''}
      <div class="actions"><button class="btn primary sm" data-act="regen">Retry</button><button class="btn sm" data-act="go-settings">Open settings</button><button class="btn sm ghost" data-act="copy-error">Copy details</button></div>
      <details><summary>Details</summary><pre>${esc(p.error || 'Unknown error')}</pre></details></div></div>`;
  } else if (p.status === 'cancelled') {
    ps.innerHTML = `<div class="status">${ico('x')}<div class="status-body"><b>Cancelled</b><p>Nothing was exported. “Try again” reruns it, and cached steps are reused.</p></div></div>`;
  } else ps.innerHTML = '';
  // one progress card: stage, percent, ETA, elapsed and the four steps (replaces the old duplicated bars)
  const prog = $('#pprog');
  if (prog) {
    prog.hidden = !(running || p.status === 'done');
    if (running) {
      const e = etaInfo(p);
      const pct = Math.max(+(prog.dataset.p || 0), e.pct); prog.dataset.p = String(pct);
      $('#pp-pct').textContent = pct + '%';
      $('#pp-stage').textContent = e.st || 'Working';
      $('#pp-sub').textContent = p.stage && p.stage !== e.st ? p.stage : (p.clips.length ? `${p.clips.length} clip${p.clips.length === 1 ? '' : 's'} so far` : '');
      $('#pp-left').textContent = e.leftTxt || 'Estimating…';
      $('#pp-left').hidden = false;
      $('#pp-el').textContent = p.started ? `Elapsed ${fmtT(Date.now() / 1000 - p.started)}` : '';
      $('#pp-el').hidden = !p.started;
      $('#pp-fill').style.width = pct + '%';
      paintSteps(stepIndex(p.stage, p.status));
    } else if (p.status === 'done') {
      prog.dataset.p = '0';
      const total = (p.finished && p.started) ? fmtT(p.finished - p.started) : '';
      $('#pp-pct').textContent = '100%';
      $('#pp-stage').textContent = 'Done';
      $('#pp-sub').textContent = `${p.clips.length} clip${p.clips.length === 1 ? '' : 's'} ready`;
      $('#pp-left').textContent = total ? `Took ${total}` : '';
      $('#pp-left').hidden = !total;
      $('#pp-el').hidden = true;
      $('#pp-fill').style.width = '100%';
      paintSteps(4);
    }
  }
  if (scan) scan.hidden = !(running || queued) || localStorage.getItem('hideScan') === '1';
  if (dash) dash.classList.toggle('run', running && !!scan && !scan.hidden);
  if (!running) hwStop();
  const tog = $('#scanToggle');
  if (tog) { tog.hidden = !running; tog.textContent = localStorage.getItem('hideScan') === '1' ? 'Show analysis' : 'Hide analysis'; }
  const cc = $('#clipCount');
  if (cc) cc.textContent = running && p.clips.length ? `${p.clips.filter(c => c.status === 'ready').length}/${p.clips.length} ready` : `${p.clips.length} clip${p.clips.length === 1 ? '' : 's'}`;
  // clips
  const grid = $('#clipgrid');
  if (grid) {
    const have = new Map($$('.clip', grid).map(e => [e.dataset.rank, e]));
    const want = new Set(p.clips.map(c => String(c.rank)));
    have.forEach((el, k) => { if (!want.has(k)) el.remove(); });
    p.clips.forEach(c => {
      const sig = [c.rev, c.status, c.title, c.last_error, (c.hashtags || []).join(','), c.start, c.end, (c.urls || {})[c.platforms[0]], c.render_pct, c.render_eta, c.thumb].join('|');
      const old = have.get(String(c.rank));
      if (old && old.dataset.sig === sig) return;
      const eln = cardEl(p, c, sig);
      if (old) old.replaceWith(eln); else grid.appendChild(eln);
    });
    const waiting = grid.querySelector('.waiting'); if (waiting) waiting.remove();
    if (!p.clips.length) {
      if (running) {
        const counts = p.counts || {}, e = etaInfo(p);
        grid.insertAdjacentHTML('afterbegin', `<div class="card waiting">
          <div class="waiting-head">${ico('sparkle')}<b>Scanning ${counts.moments ?? '…'} moments · ${counts.short ?? 0} shortlisted</b></div>
          <div class="bar"><i style="width:${e.pct}%"></i></div>
          <p class="hint">${esc(e.st || 'Starting')} · ${esc(e.leftTxt || 'estimating…')}</p>
          ${p.strip ? `<img class="waiting-strip" src="/api/projects/${p.id}/strip" alt="" onerror="this.remove()">` : ''}</div>`);
      } else if (p.status === 'done') {
        grid.innerHTML = `<div class="empty big">${ico('film')}<div><b>No clips left</b><span class="hint">Deleted clips don’t come back. Regenerate to make new ones.</span></div></div>`;
      }
    }
  }
}
const scoreCls = s => s >= .7 ? 'hi' : s >= .5 ? 'mid' : 'lo';
function cardEl(p, c, sig) {
  const el = document.createElement('article');
  el.className = 'clip';
  el.dataset.rank = c.rank; el.dataset.sig = sig;
  const plat0 = (c.platforms || [])[0];
  const ready = c.status !== 'rendering' && c.urls && c.urls[plat0];
  if (!ready) {
    el.classList.add('is-rendering');
    const pct = Math.round((c.render_pct || 0) * 100);
    const sub = c.render_eta != null ? `${pct}% · ~${fmtT(c.render_eta)} left` : (pct > 0 ? `${pct}%` : 'Queued');
    el.innerHTML = `<div class="vid">${c.rank ? `<img src="/api/projects/${p.id}/clips/${c.rank}/pre.jpg" alt="" onerror="this.remove()">` : ''}<div class="shade"></div>
        <div class="ring" style="--p:${pct}"><b>${pct}%</b></div></div>
      <div class="cbody"><h3 dir="auto">${esc(c.title || 'Clip #' + c.rank)}</h3>
        <div class="cmeta"><span>Rendering · ${sub}</span></div><div class="bar thin"><i style="width:${pct}%"></i></div></div>`;
    return el;
  }
  el.dataset.plat = plat0;
  const sc = Math.round(c.score * 100);
  const tags = (c.hashtags || []).slice(0, 3).map(t => `#${esc(t)}`).join(' ');
  el.innerHTML = `<div class="vid" data-act="view-clip">
      <video muted playsinline preload="metadata" ${c.thumb ? `poster="${c.thumb}"` : ''} src="${c.urls[plat0]}"></video>
      <div class="score ${scoreCls(c.score)}" style="--v:${sc}" title="Marrow score: how strongly this moment ranked"><span>${sc}</span></div>
      <span class="dur">${fmtT(c.duration)}</span>
      <button class="expand" data-act="view-clip" title="Watch fullscreen" aria-label="Watch fullscreen">${ico('expand')}</button>
    </div>
    <div class="cbody">
      <h3 dir="auto" title="${esc(c.title)}">${esc(c.title)}</h3>
      ${c.platforms.length > 1 ? `<div class="plat-seg" role="group" aria-label="Format">${c.platforms.map(pl => `<button type="button" data-act="clip-plat" data-plat="${pl}" class="${pl === plat0 ? 'on' : ''}">${pl === 'shorts' ? 'Shorts' : 'Reels'}</button>`).join('')}</div>` : ''}
      <div class="cmeta">${tags ? `<span>${tags}</span>` : '<span>No hashtags</span>'}</div>
      ${c.last_error ? `<div class="cerr">Last re-render failed: ${esc(c.last_error)}</div>` : ''}
      <div class="cactions">
        <button class="btn primary sm" data-act="download-clip">${ico('download')}Download</button>
        <button class="btn sm" data-act="edit-clip">${ico('pen')}Edit</button>
        <details class="menu"><summary class="btn sm" title="More actions" aria-label="More actions">${ico('more', 'fill')}</summary>
          <div class="pop">
            <button type="button" data-act="export-clip">${ico('upload')}Export…</button>
            <button type="button" data-act="subs-clip">${ico('type')}Subtitles</button>
            <button type="button" data-act="copy-title">${ico('copy')}Copy title</button>
            <button type="button" data-act="copy-caption">${ico('copy')}Copy caption + tags</button>
            <button type="button" class="danger" data-act="del-clip">${ico('trash')}Delete clip</button>
          </div></details>
      </div>
    </div>`;
  return el;
}
function clipOf(btn) { const el = btn.closest('.tile,.clip'); const p = curProject(); return { el, p, c: p.clips.find(x => String(x.rank) === el.dataset.rank) }; }
function downloadClip(pid, plat, c) {
  const src = c.urls[plat] || c.urls[c.platforms[0]];
  if (!src) { toast('Nothing to download yet.', 'info'); return; }
  const base = src.split('?')[0];
  const filename = decodeURIComponent(base.split('/').pop() || `clip_${c.rank}.mp4`);
  const a = document.createElement('a');
  a.href = base + '?download=1';
  a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  toast('Downloading…', 'ok');
}
/* ---------- fullscreen viewer ---------- */
const Viewer = (() => {
  let el, list = [], i = 0;
  const build = () => {
    el = document.createElement('div'); el.className = 'viewer'; el.hidden = true;
    el.innerHTML = `<button class="vx" aria-label="Close">✕</button><button class="vp">‹</button><button class="vn">›</button>
      <div class="vbox"><video controls playsinline autoplay></video><div class="vt" dir="auto"></div></div>
      <div class="vbar"><button class="btn sm vfs">Fullscreen</button><button class="btn sm primary vdl">Download</button></div>`;
    document.body.appendChild(el);
    el.querySelector('.vx').onclick = close; el.querySelector('.vp').onclick = () => go(-1); el.querySelector('.vn').onclick = () => go(1);
    el.querySelector('.vfs').onclick = () => { const b = el.querySelector('.vbox'); document.fullscreenElement ? document.exitFullscreen() : b.requestFullscreen(); };
    el.querySelector('.vdl').onclick = e => {
      const c = list[i];
      if (e.shiftKey) openExport(c.pid, [c.rank], false);
      else quickExport(c.pid, c.rank);
    };
    el.addEventListener('click', e => { if (e.target === el) close(); });
    document.addEventListener('keydown', e => { if (el.hidden) return;
      if (e.key === 'Escape' && !document.fullscreenElement) close();
      if (e.key === 'ArrowRight') go(1); if (e.key === 'ArrowLeft') go(-1);
      if (e.key.toLowerCase() === 'f') el.querySelector('.vfs').click(); });
  };
  const show = () => { const c = list[i], v = el.querySelector('video');
    v.src = c.url; v.play().catch(() => {});
    const t = el.querySelector('.vt'); t.textContent = '';
    t.append(document.createTextNode(c.title));
    const b = document.createElement('button'); b.className = 'vcopy'; b.title = 'Copy title';
    b.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>';
    b.onclick = e => { e.stopPropagation(); copyText(c.title, 'Title copied'); };
    t.append(b); };
  const go = d => { i = (i + d + list.length) % list.length; show(); };
  const close = () => { el.hidden = true; el.querySelector('video').pause(); };
  const quickExport = async (pid, rank) => {
    const q = lastQuality() || state.settings?.settings?.export?.default_quality || '1080p';
    close();
    try {
      const r = await api(`/api/projects/${pid}/clips/${rank}/export`, { method: 'POST', body: { quality: q } });
      toast('Exporting…');
      const poll = setInterval(async () => {
        try {
          const st = await api(`/api/projects/${pid}/exports/${r.id}`);
          if (st.state === 'done') {
            clearInterval(poll);
            const a = document.createElement('a');
            a.href = `/api/projects/${pid}/exports/${r.id}/file`; a.download = '';
            document.body.appendChild(a); a.click(); a.remove();
            toast('Export ready', 'ok');
          } else if (st.state === 'error') { clearInterval(poll); toast(st.error || 'Export failed', 'bad'); }
        } catch (e) { clearInterval(poll); toast(e.message, 'bad'); }
      }, 1500);
    } catch (e) { toast(e.message, 'bad'); }
  };
  return { open(clips, idx) { if (!el) build(); list = clips; i = idx; el.hidden = false; show(); } };
})();
/* ---------- live analysis scan + hardware polling ---------- */
/* ---------- media that may still be produced: retry with back-off instead of failing silently ---------- */
function mountVideo(v, url, onFail) {
  v.dataset.src = url; v.dataset.tries = '0';
  const attach = () => { v.src = url + (url.includes('?') ? '&' : '?') + 'try=' + v.dataset.tries; v.load(); };
  v.onerror = () => {
    if (v.dataset.src !== url) return;
    const n = (+v.dataset.tries || 0) + 1; v.dataset.tries = String(n);
    if (n <= 8) setTimeout(() => { if (v.dataset.src === url) attach(); }, Math.min(6000, 700 * n));
    else if (onFail) onFail();
  };
  v.onloadeddata = () => { v.dataset.tries = '0'; };
  attach();
}
function unmountVideo(v) {
  if (!v) return;
  v.onerror = null; v.onloadeddata = null; v.ontimeupdate = null;
  delete v.dataset.src;
  v.removeAttribute('src'); v.load();
}
function paintScanPlay() {
  const v = document.getElementById('scanVideo'), b = document.getElementById('scanPlay');
  if (!b || !v) return;
  b.innerHTML = ico(v.paused ? 'play' : 'pause', 'fill');
  b.title = v.paused ? 'Play preview' : 'Pause preview';
  b.setAttribute('aria-label', b.title);
}

/* ---------- live analysis panel ---------- */
const Scan = (() => {
  const $id = id => document.getElementById(id);
  function reset() {
    unmountVideo($id('scanVideo'));
    const lb = $id('logbody'); if (lb) lb.innerHTML = '';
    const mk = $id('marks'); if (mk) mk.innerHTML = '';
    const n = $id('scanNote'); if (n) n.hidden = true;
    update._lc = null;
  }
  function mount() { reset(); }
  function update(p, lines) {
    const root = $id('scan'); if (!root) return;
    const v = $id('scanVideo'), st = p.stage || '';
    const running = p.status === 'running';
    const live = running && /render|encod|caption|clip \d/i.test(st);
    root.dataset.state = !running ? 'idle' : live ? 'live' : 'scanning';
    $id('scanPill').textContent = running ? (live ? 'Rendering' : 'Analysing') : 'Idle';
    if (v && p.proxy && !v.dataset.src) {
      mountVideo(v, `/api/projects/${p.id}/proxy`, () => {
        const n = $id('scanNote');
        if (n) { n.hidden = false; n.textContent = 'The live preview couldn’t load. Analysis keeps running.'; }
      });
    }
    const strip = $id('strip');
    if (strip) strip.hidden = !p.strip;
    const si = $id('stripImg'); if (si && p.strip && !si.getAttribute('src')) si.src = `/api/projects/${p.id}/strip`;
    $id('scanLabel').textContent = /download|prepar|extract/i.test(st) ? 'Downloading' : /transcrib/i.test(st) ? 'Transcribing audio' : /scor|analy|rank/i.test(st) ? 'Ranking moments' : 'Scanning content';
    $id('trs').textContent = /transcrib/i.test(st) ? 'processing' : 'done';
    $id('thr').textContent = running ? 'active' : 'idle';
    const dur = (p.scan && p.scan.dur) || (v && v.duration) || 1;
    const ph = $id('playhead');
    const ready = !!(v && v.dataset.src);
    if (ready && root.dataset.state === 'scanning') {
      if (p.scan) {
        if (Math.abs(v.currentTime - p.scan.t) > 3) { try { v.currentTime = p.scan.t; } catch (_) {} }
        v.play().catch(() => {});
        if (ph) ph.style.left = (p.scan.t / dur * 100) + '%';
      } else {
        v.muted = true; v.play().catch(() => {});
        v.ontimeupdate = () => { if (v.currentTime > 60) { try { v.currentTime = 0; } catch (_) {} } };
      }
    }
    if (ready && live) {
      const c = (p.clips || []).find(x => x.status === 'rendering');
      if (c && update._lc !== c.rank) {
        update._lc = c.rank;
        try { v.currentTime = c.start; } catch (_) {}
        v.play().catch(() => {});
        v.ontimeupdate = () => { if (v.currentTime > c.end) { try { v.currentTime = c.start; } catch (_) {} } };
      }
      if (c && ph) ph.style.left = (c.start / dur * 100) + '%';
    }
    const mk = $id('marks');
    if (mk) mk.innerHTML = (p.candidates || []).map(c =>
      `<i style="left:${c.s / dur * 100}%;width:${Math.max(.4, (c.e - c.s) / dur * 100)}%;background:${c.score >= 70 ? 'var(--ok)' : c.score >= 45 ? 'var(--warn)' : '#6b6b76'}"></i>`).join('');
    if (lines && lines.length) {
      const box = $id('logbody');
      const stick = box.scrollTop + box.clientHeight >= box.scrollHeight - 20;
      lines.forEach(l => {
        const m = /^\s*(\[.*?\])\s?([\s\S]*)$/.exec(l);
        const d = document.createElement('div');
        if (m) {
          const ts = document.createElement('bdi'); ts.dir = 'ltr'; ts.textContent = m[1];
          const tx = document.createElement('bdi'); tx.dir = 'auto'; tx.textContent = ' ' + m[2];
          d.append(ts, tx);
        } else d.textContent = l;
        box.appendChild(d);
      });
      while (box.children.length > 300) box.firstChild.remove();
      if (stick) box.scrollTop = box.scrollHeight;
    }
    paintScanPlay();
  }
  return { mount, update, reset };
})();

/* ---------- hardware meters (one compact row; no duplicated detail panel) ---------- */
let _hwT = null;
function paintHw(d) {
  const slot = document.getElementById('hw-slot'); if (!slot) return;
  const eng = d.engines || {};
  const t = eng.transcribe, r = eng.render, l = eng.llm;
  const isGpu = e => e && (e.device === 'cuda' || e.device === 'gpu');
  const chip = e => e ? `<span class="chip ${isGpu(e) ? 'ok' : 'warn'}">${isGpu(e) ? 'GPU' : 'CPU'}</span>` : '';
  const heads = [];
  if (t) heads.push(`${chip(t)} Whisper · ${esc(t.model || '')}`);
  if (r) heads.push(`${chip(r)} Encode · ${esc(r.encoder || r.label || '')}`);
  if (l && l.device !== 'off') heads.push(`${chip(l)} AI · ${esc(l.model || '')}`);
  const fb = [t, r].filter(e => e && e.fallback).map(e => e.fallback)[0];
  const g = d.gpu;
  const meter = (label, pct, text) => `<span class="meter">${label}<i><b style="width:${Math.min(100, pct || 0)}%"></b></i><em>${text}</em></span>`;
  slot.innerHTML = `<div class="hwrow">${heads.join('<span class="sep">·</span>') || '<span>Preparing engines…</span>'}</div>
    <div class="hwrow meters">${g ? meter('GPU', g.percent, g.percent + '%') : ''}${g ? meter('VRAM', g.vram_percent, `${g.vram_used_gb}/${g.vram_total_gb} GB`) : ''}${meter('CPU', d.cpu.percent, d.cpu.percent + '%')}${meter('RAM', d.ram.percent, `${d.ram.used_gb}/${d.ram.total_gb} GB`)}</div>
    ${fb ? `<div class="hw-warn">Fell back to CPU: ${esc(fb)}</div>` : ''}`;
}
function hwStart() {
  hwStop();
  const tick = async () => { try { paintHw(await (await fetch('/api/hardware')).json()); } catch (e) {} };
  tick(); _hwT = setInterval(tick, 1000);
}
function hwStop() { if (_hwT) clearInterval(_hwT); _hwT = null; }
let _rp = false;
async function refreshProject(id) {
  if (_rp) return; _rp = true;
  try {
    const cur = state.projects.find(x => x.id === id);
    const from = cur?.logTotal || 0;
    const np = await api(`/api/projects/${id}?log_from=${from}`);
    const lines = np.log || [];
    const i = state.projects.findIndex(x => x.id === id);
    const merged = { ...(i >= 0 ? state.projects[i] : {}), ...np };
    merged.log = ((i >= 0 ? state.projects[i].log : []) || []).concat(lines);
    merged.logTotal = np.log_total ?? merged.log.length;
    if (i >= 0) state.projects[i] = merged; else state.projects.unshift(merged);
    renderSide();
    if (state.route.name === 'project' && state.route.id === id) {
      paintProject(merged);
      Scan.update(merged, lines);
    }
    if (!ACTIVE.has(merged.status)) hwStop();
    if (merged.status === 'done' && cur?.status !== 'done') onJobDone(merged);
  } catch (_) {} finally { _rp = false; }
}

/* ----- edit modal ----- */
function openEdit(p, c, tab = 'trim') {
  const cs = c.style || p.settings.caption_style || {};
  const m = openModal(`<h3>Edit clip #${c.rank}</h3><p class="desc">Adjust where the clip starts and ends, fix caption words, or change the title. Re-rendering uses your cached transcript.</p>
    <div class="tabs"><button class="on" data-tab="trim">Trim</button><button data-tab="caps">Captions</button><button data-tab="info">Title &amp; tags</button></div>
    <div data-pane="trim"><div class="edgrid"><div><div class="livewrap"><video id="ed-src" controls preload="metadata" src="/source/${p.video_id}"></video></div>
        <div class="note" id="ed-vnote">Scrub the source video, then use “Set start/end from playhead”.</div></div>
      <div><div class="trimrow">
        <div class="fieldx"><span class="fl">Start (s)</span><input type="number" id="ed-start" step="0.1" min="0" value="${c.start}"></div>
        <div class="fieldx"><span class="fl">End (s)</span><input type="number" id="ed-end" step="0.1" min="0" value="${c.end}"></div>
        <div class="fieldx"><span class="fl">Length</span><b id="ed-len" style="padding:9px 0"></b></div></div>
        <div class="actions"><button class="btn sm" id="ed-sets">Set start from playhead</button><button class="btn sm" id="ed-sete">Set end from playhead</button><button class="btn sm" id="ed-prev">▶ Preview selection</button></div>
        <label class="tog" style="margin-top:8px"><input type="checkbox" id="ed-livecap" checked><span class="knob"></span><span class="tl">Caption preview<small>HTML overlay on the raw source (no burned-in captions here)</small></span></label>
        <p class="note">Clips must be at least 5 seconds. Start and end are positions in the source video.</p></div></div></div>
    <div data-pane="caps" hidden>
      ${stylePickerHTML(cs.preset, `<div><img class="capprev capPrev" alt="" hidden><div class="note capPrevNote">Pick a style for a real-frame preview</div></div>`)}
      <div class="custwrap">${customizeHTML(cs.overrides, cs.preset)}</div>
      <div class="form" style="margin-top:12px"><div class="field">${tog('ed-cap', 'Burn in captions', true)}</div></div>
      <div class="fl" style="margin:16px 0 8px">Caption text <span style="font-weight:400">(edit any word; changed words are highlighted)</span></div>
      <div class="words" id="ed-words" dir="auto"><span class="note">Loading words…</span></div>
      <div class="fl" style="margin:12px 0 6px">Word timing <span style="font-weight:400">(drag to move, drag edges to trim)</span></div>
      <div class="wtl" id="ed-tl"></div>
      <div class="actions" style="margin-top:10px"><button class="btn sm" id="ed-reload">Reload words for current start/end</button></div></div>
    <div data-pane="info" hidden><div class="form"><div class="field full"><span class="fl">Title</span><input class="txt" id="ed-title" dir="auto" maxlength="120" value="${esc(c.title)}"></div>
      <div class="field full"><span class="fl">Hashtags (comma or space separated)</span><input class="txt" id="ed-tags" dir="auto" value="${esc(c.hashtags.join(', '))}"></div></div>
      <div class="actions" style="margin-top:12px"><button class="btn" id="ed-saveinfo">Save title &amp; tags</button></div></div>
    <div class="mfoot"><button class="btn ghost" id="ed-cancel">Close</button><button class="btn primary" id="ed-go">Save &amp; re-render</button></div>`, true);
  const v = $('#ed-src', m), S = $('#ed-start', m), E = $('#ed-end', m);
  const upd = () => { const d = (+E.value) - (+S.value); $('#ed-len', m).textContent = isNaN(d) ? '—' : d.toFixed(1) + 's'; $('#ed-len', m).style.color = d >= 5 ? '' : 'var(--bad)'; };
  S.oninput = E.oninput = upd; upd();
  v.addEventListener('loadedmetadata', () => { v.currentTime = c.start; });
  v.addEventListener('error', () => { $('#ed-vnote', m).textContent = 'This browser can\'t play the source file, so enter start/end times manually.'; });
  $('#ed-sets', m).onclick = () => { S.value = v.currentTime.toFixed(2); upd(); };
  $('#ed-sete', m).onclick = () => { E.value = v.currentTime.toFixed(2); upd(); };
  $('#ed-prev', m).onclick = () => { v.currentTime = +S.value; v.play(); const stop = () => { if (v.currentTime >= +E.value) { v.pause(); v.removeEventListener('timeupdate', stop); } }; v.addEventListener('timeupdate', stop); };
  const showTab = (t) => { $$('.tabs button', m).forEach(x => x.classList.toggle('on', x.dataset.tab === t)); $$('[data-pane]', m).forEach(pn => pn.hidden = pn.dataset.pane !== t); };
  $$('.tabs button', m).forEach(b => b.onclick = () => showTab(b.dataset.tab));
  showTab(tab);
  editCtx = { pid: p.id, rank: c.rank, t: c.start + 1 };
  const syncCtx = () => { editCtx = { pid: p.id, rank: c.rank, t: v.currentTime }; previewReal(m); };
  v.addEventListener('seeked', syncCtx); v.addEventListener('pause', syncCtx);
  mountStyles(m, cs.preset || 'bold-pop');
  previewReal(m);
  const words = new Map(); let wordsArr = []; const timings = {};
  const liveOn = () => $('#ed-livecap', m)?.checked !== false;
  const burnOn = () => $('[data-opt="ed-cap"]', m)?.checked !== false;
  const editWords = () => {                          // the words as they now read, so a typed fix shows at once
    const cur = new Map(); $$('#ed-words input', m).forEach(i => cur.set(String(i.dataset.i), i.value.trim()));
    return wordsArr.map(w => (cur.get(String(w.i)) ? { ...w, t: cur.get(String(w.i)) } : w));
  };
  const wrap = v.parentElement;                      // .livewrap: the video's own box, where the caption is placed
  new PvOverlay({ host: wrap, video: v, words: editWords,
    read: () => { const d = readStyleRoot(m); return { preset: d.preset, ov: d.overrides, captions: liveOn() && burnOn(), platform: clipPlatform(p, c) }; } });
  async function loadWords() {
    const box = $('#ed-words', m); box.innerHTML = '<span class="note">Loading words…</span>';
    try {
      const d = await api(`/api/projects/${p.id}/clips/${c.rank}/transcript?start=${encodeURIComponent(S.value)}&end=${encodeURIComponent(E.value)}`);
      words.clear(); box.innerHTML = ''; wordsArr = d.words;
      d.words.forEach(w => {
        words.set(w.i, w.t); const inp = document.createElement('input'); inp.value = w.t; inp.dataset.i = w.i; inp.size = Math.max(3, w.t.length);
        inp.setAttribute('dir', 'auto'); inp.title = fmtT(w.s); inp.oninput = () => { inp.classList.toggle('chg', inp.value.trim() !== words.get(w.i)); inp.size = Math.max(3, inp.value.length); };
        box.appendChild(inp);
      });
      if (!d.words.length) box.innerHTML = '<span class="note">No words in this range.</span>';
      else pvSync();
      paintTimeline();
    } catch (e) { box.innerHTML = `<span class="note">${esc(e.message)}</span>`; }
  }
  function paintTimeline() {
    const tl = $('#ed-tl', m); if (!tl) return;
    const s0 = +S.value, s1 = +E.value, span = Math.max(0.1, s1 - s0);
    tl.innerHTML = '';
    wordsArr.forEach(w => {
      const b = document.createElement('div');
      b.className = 'tlb'; b.dataset.i = w.i; b.title = `${fmtT(w.s)} → ${fmtT(w.e)}`;
      b.style.left = Math.max(0, (w.s - s0) / span * 100) + '%';
      b.style.width = Math.max(1.2, (w.e - w.s) / span * 100) + '%';
      tl.appendChild(b);
    });
  }
  $('#ed-tl', m)?.addEventListener('pointerdown', e => {
    const b = e.target.closest('.tlb'); if (!b) return;
    const i = +b.dataset.i, w = wordsArr.find(x => x.i === i); if (!w) return;
    const s0 = +S.value, s1 = +E.value, span = Math.max(0.1, s1 - s0);
    const r = $('#ed-tl', m).getBoundingClientRect();
    const edge = (e.clientX - r.left) / r.width * span + s0 - w.s < 0.35 ? 'l'
      : (w.e - ((e.clientX - r.left) / r.width * span + s0)) < 0.35 ? 'r' : 'm';
    const x0 = e.clientX, os = w.s, oe = w.e;
    b.setPointerCapture(e.pointerId);
    const move = ev => {
      const dt = (ev.clientX - x0) / r.width * span;
      let ns = os, ne = oe;
      if (edge === 'l') ns = Math.min(os + dt, oe - 0.05);
      else if (edge === 'r') ne = Math.max(oe + dt, os + 0.05);
      else { ns = os + dt; ne = oe + dt; }
      ns = Math.max(s0 - 2, ns); ne = Math.min(s1 + 2, ne);
      if (ne - ns < 0.05) return;
      w.s = +ns.toFixed(2); w.e = +ne.toFixed(2);
      timings[i] = [w.s, w.e];
      b.style.left = Math.max(0, (w.s - s0) / span * 100) + '%';
      b.style.width = Math.max(1.2, (w.e - w.s) / span * 100) + '%';
      b.title = `${fmtT(w.s)} → ${fmtT(w.e)}`;
    };
    const up = () => { b.removeEventListener('pointermove', move); b.removeEventListener('pointerup', up); };
    b.addEventListener('pointermove', move); b.addEventListener('pointerup', up);
  });
  $('#ed-reload', m).onclick = loadWords; loadWords();
  $('#ed-cancel', m).onclick = closeModal;
  $('#ed-saveinfo', m).onclick = async () => {
    try { const np = await api(`/api/projects/${p.id}/clips/${c.rank}`, { method: 'PATCH', body: { title: $('#ed-title', m).value, hashtags: $('#ed-tags', m).value } });
      mergeProject(np); toast('Saved', 'ok'); } catch (e) { toast(e.message, 'bad'); }
  };
  $('#ed-go', m).onclick = async () => {
    const edits = {}; $$('#ed-words input', m).forEach(i => { if (i.value.trim() && i.value.trim() !== words.get(+i.dataset.i)) edits[i.dataset.i] = i.value.trim(); });
    const btn = $('#ed-go', m); btn.disabled = true;
    const st = state.projects.find(x => x.id === p.id);
    const sc = st?.clips.find(x => x.rank === c.rank);
    if (sc) { sc.status = 'rendering'; if (state.route.name === 'project') paintProject(st); }
    try {
      const np = await api(`/api/projects/${p.id}/clips/${c.rank}/rerender`, { method: 'POST', body: {
        start: +S.value, end: +E.value, captions: $('[data-opt="ed-cap"]', m).checked, edits, timings,
        style: { preset: $('.stylePreset', m)?.value || 'bold-pop', overrides: collectOverrides(m) } } });
      mergeProject(np); closeModal(); toast('Re-rendering clip…');
    } catch (e) { toast(e.message, 'bad'); btn.disabled = false; if (sc) { sc.status = 'ready'; if (state.route.name === 'project') paintProject(st); } }
  };
}
function lastQuality() {
  try { return localStorage.getItem('exportQuality') || null; } catch (_) { return null; }
}
function openExport(pid, ranks, batch) {
  const p = state.projects.find(x => x.id === pid); if (!p) return;
  const clips = p.clips.filter(c => ranks.includes(c.rank));
  if (!clips.length) { toast('No clips to export.', 'bad'); return; }
  const q0 = lastQuality() || state.settings?.settings?.export?.default_quality || '1080p';
  const styleOpts = [`<option value="current">Clip's current style</option>`,
    ...Object.entries(STYLES.presets || {}).map(([k, v]) => `<option value="${k}">${v.label || k}</option>`)].join('');
  const m = openModal(`<div class="exmodal"><h3>Export ${batch ? clips.length + ' clips' : '1 clip'}</h3>
    <div class="form">
      <div class="field"><span class="fl">Format</span><div class="seg" id="ex-fmt"><button type="button" class="on" data-v="mp4">MP4 (H.264)</button><button type="button" data-v="mov">MOV</button></div></div>
      <div class="field"><span class="fl">Quality</span><select id="ex-q" class="txt">
        ${[['480p', '480p · Data saver'], ['720p', '720p · Standard'], ['1080p', '1080p · High'], ['1440p', '1440p · Max'], ['source', 'Source · Match original']].map(([v, l]) => `<option value="${v}" ${v === q0 ? 'selected' : ''}>${l}</option>`).join('')}</select></div>
    </div>
    <details id="ex-adv"><summary style="cursor:pointer;color:var(--muted);font-weight:600;margin-top:10px">Advanced</summary>
      <div class="form" style="margin-top:10px">
        <div class="field"><span class="fl">CRF (lower = better)</span><input type="number" id="ex-crf" min="16" max="32" placeholder="auto"></div>
        <div class="field"><span class="fl">Video Mbps cap</span><input type="number" id="ex-mbps" min="1" max="80" step="0.5" placeholder="auto"></div>
        <div class="field"><span class="fl">Audio kbps</span><input type="number" id="ex-ab" min="64" max="320" step="32" placeholder="160"></div>
        <div class="field"><span class="fl">FPS cap</span><div class="seg" id="ex-fps"><button type="button" class="on" data-v="0">Source</button><button type="button" data-v="30">30</button><button type="button" data-v="60">60</button></div></div>
      </div></details>
    <div class="form" style="margin-top:10px">
      <div class="field"><div class="exrow"><span class="tl" style="flex:1">Include captions</span><label class="tog"><input type="checkbox" id="ex-cap" checked><span class="knob"></span></label></div></div>
      <div class="field"><span class="fl">Caption style</span><div style="display:flex;gap:8px"><select id="ex-style" class="txt" style="flex:1">${styleOpts}</select><button class="btn sm" id="ex-edtext">Edit text…</button></div></div>
      <div class="field full" id="ex-wordsWrap" hidden><div class="words" id="ex-words"><span class="note">Loading…</span></div></div>
      <div class="field" style="grid-column:1/-1"><span class="fl">Framing</span><div class="seg" id="ex-frame"><button type="button" class="on" data-v="auto">Auto</button><button type="button" data-v="crop">Center crop</button><button type="button" data-v="blur_fit">Blur fill</button></div></div>
      <div class="field"><div class="exrow"><span class="tl" style="flex:1">Watermark<small>None</small></span><label class="tog"><input type="checkbox" disabled><span class="knob"></span></label></div></div>
      ${batch ? `<div class="field full"><div class="exrow"><span class="tl" style="flex:1">Apply to all clips<small>Off = each clip keeps its own style</small></span><label class="tog"><input type="checkbox" id="ex-all" checked><span class="knob"></span></label></div></div>` : ''}
    </div>
    <div class="exsum" id="ex-sum" style="margin-top:10px"></div>
    <div class="upbar" id="ex-bar" hidden style="margin-top:8px"><i></i></div>
    <div class="note" id="ex-note"></div><div class="note" id="ex-enc" style="margin-top:4px"></div>
    <div class="mfoot exfoot"><button class="btn ghost" id="ex-no">Cancel</button><button class="btn primary" id="ex-go">Export</button></div></div>`, true);
  const segVal = id => { const b = $(`#${id} .on`, m); return b ? b.dataset.v : ''; };
  const exSum = () => {
    const q = $('#ex-q', m).value, f = segVal('ex-fmt') === 'mov' ? 'MOV' : 'MP4';
    const fr = segVal('ex-frame'), frTxt = fr === 'crop' ? 'center crop' : fr === 'blur_fit' ? 'blur fill' : 'as rendered';
    $('#ex-sum', m).textContent = `${q} · ${f} · ${frTxt}${$('#ex-cap', m).checked ? '' : ' · no captions'}`;
  };
  ['ex-q', 'ex-cap'].forEach(id => $('#' + id, m)?.addEventListener('change', exSum));
  m.addEventListener('click', e => { if (e.target.closest('.seg')) exSum(); });
  exSum();
  $$('#ex-fmt button,#ex-fps button,#ex-frame button', m).forEach(b => b.onclick = () => {
    $$('button', b.parentElement).forEach(x => x.classList.toggle('on', x === b)); });
  $('#ex-no', m).onclick = closeModal;
  const wcache = new Map();
  $('#ex-edtext', m).onclick = async () => {
    const box = $('#ex-words', m), wrap = $('#ex-wordsWrap', m);
    wrap.hidden = !wrap.hidden;
    if (!wrap.hidden && !box.dataset.loaded) {
      try {
        const c0 = clips[0];
        const d = await api(`/api/projects/${pid}/clips/${c0.rank}/transcript?start=${c0.start}&end=${c0.end}`);
        box.innerHTML = '';
        d.words.forEach(w => { wcache.set(w.i, w.t);
          const inp = document.createElement('input'); inp.value = w.t; inp.dataset.i = w.i; inp.size = Math.max(3, w.t.length); inp.dir = 'auto';
          box.appendChild(inp); });
        box.dataset.loaded = '1';
      } catch (e) { box.innerHTML = `<span class="note">${esc(e.message)}</span>`; }
    }
  };
  $('#ex-go', m).onclick = async () => {
    const btn = $('#ex-go', m); btn.disabled = true;
    const bar = $('#ex-bar', m); bar.hidden = false;
    const note = $('#ex-note', m), encEl = $('#ex-enc', m);
    const num = id => { const v = $(`#${id}`, m).value; return v === '' ? null : +v; };
    const edits = {};
    $$('#ex-words input', m).forEach(i => { if (i.value.trim() !== (wcache.get(+i.dataset.i) ?? i.value)) edits[i.dataset.i] = i.value.trim(); });
    const body = {
      format: segVal('ex-fmt') || 'mp4',
      quality: $('#ex-q', m).value,
      captions: $('#ex-cap', m).checked,
      style: { preset: $('#ex-style', m).value === 'current' ? null : $('#ex-style', m).value, overrides: {} },
      edits, framing: segVal('ex-frame') || null,
      advanced: { crf: num('ex-crf'), video_mbps: num('ex-mbps'), audio_kbps: num('ex-ab'), fps: +segVal('ex-fps') || 0 },
    };
    if (batch) body.apply_to_all = $('#ex-all', m).checked;
    try { localStorage.setItem('exportQuality', body.quality); } catch (_) {}
    try { await api('/api/settings', { method: 'PUT', body: { export: { default_quality: body.quality } } }); } catch (_) {}
    const url = batch ? `/api/projects/${pid}/export` : `/api/projects/${pid}/clips/${clips[0].rank}/export`;
    const payload = batch ? { ...body, clip_ids: ranks } : body;
    let job;
    try {
      const r = await api(url, { method: 'POST', body: payload });
      job = r.id;
    } catch (e) { note.textContent = e.message; btn.disabled = false; return; }
    const poll = setInterval(async () => {
      try {
        const st = batch
          ? await api(`/api/projects/${pid}/exports/${job}`)
          : await api(`/api/projects/${pid}/exports/${job}`);
        const pct = Math.round((st.progress || 0) * 100);
        $('i', bar).style.width = pct + '%';
        note.textContent = st.state === 'running' ? `Exporting… ${pct}%` : st.state;
        if (st.encoder && st.encoder !== 'cached') encEl.textContent = 'Engine: ' + st.encoder;
        else if (st.encoder === 'cached') encEl.textContent = 'Served from cache (instant)';
        if (st.state === 'done') {
          clearInterval(poll); closeModal();
          const a = document.createElement('a');
          a.href = `/api/projects/${pid}/exports/${job}/file`; a.download = '';
          document.body.appendChild(a); a.click(); a.remove();
          toast('Export ready', 'ok');
        } else if (st.state === 'error') {
          clearInterval(poll); note.textContent = st.error || 'Export failed'; btn.disabled = false;
        }
      } catch (e) { clearInterval(poll); note.textContent = e.message; btn.disabled = false; }
    }, 1500);
  };
}
/* ---------- Edits workspace ---------- */
const Edits = { active: false, pid: null, rank: null, words: [], wav: null, dirty: false, undo: [], redo: [], overlay: null, loop: null };
function viewEdits() {
  Edits.active = true;
  document.removeEventListener('keydown', edxKeys);
  const projs = state.projects.filter(p => p.clips && p.clips.length);
  if (!projs.length) {
    main.innerHTML = `<header class="page-head"><div><div class="eyebrow">Workspace</div><h1 class="page-title">Edits</h1><p class="page-sub">Captions, framing, trim and words, with a live preview.</p></div></header>
      <div class="empty big">${ico('pen')}<div><b>Nothing to edit yet</b><span class="hint">Generate clips from a video first. They’ll appear here.</span></div><a class="btn primary sm" href="#/">Start a project</a></div>`;
    return;
  }
  main.innerHTML = `<header class="page-head">
      <div><div class="eyebrow">Workspace</div><h1 class="page-title">Edits</h1><p class="page-sub">Captions, framing, trim and words. Save, then re-render just this clip.</p></div>
      <div class="head-actions">
        <span class="pill warn" id="ed-dirty" hidden>Unsaved changes</span>
        <button class="btn sm" id="edx-undo" title="Undo (Ctrl+Z)">${ico('undo')}Undo</button>
        <button class="btn sm" id="edx-redo" title="Redo (Ctrl+Shift+Z)">${ico('redo')}Redo</button>
        <button class="btn sm" id="edx-save">${ico('check')}Save</button>
        <button class="btn primary sm" id="edx-export">${ico('download')}Export</button>
      </div></header>
    <div class="ed-pick card">
      <label class="pick"><span class="label">Project</span><select id="edx-proj">${projs.map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join('')}</select></label>
      <label class="pick"><span class="label">Clip</span><select id="edx-clip"></select></label>
    </div>
    <div class="ed-grid">
      <section class="card ed-stage">
        <div class="phone" id="edx-wrap"><video id="edx-v" playsinline preload="auto"></video></div>
        <div class="transport">
          <button class="icon" id="edx-playbtn" type="button" aria-label="Play">${ico('play', 'fill')}</button>
          <input type="range" id="edx-seek" min="0" max="1000" value="0" aria-label="Seek">
          <span class="time mono" id="edx-time">0:00 / 0:00</span>
        </div>
        <p class="hint" id="edx-note" hidden></p>
        <div class="ed-acc"><button class="btn sm" id="edx-acc" type="button">${ico('sparkle')}Accurate preview</button><span class="hint">Overlay is instant. “Accurate” renders one real frame.</span></div>
        <img id="edx-img" class="capprev" alt="" hidden>
      </section>
      <section class="card ed-inspect edside">
        <div class="tabs" id="edx-tabs"><button class="on" data-tab="caps">Captions</button><button data-tab="frame">Framing</button><button data-tab="trim">Trim</button><button data-tab="text">Words</button></div>
        <div data-pane="caps">
          ${stylePickerHTML('bold-pop', '', 'id="edx-preset"')}
          <div class="custwrap" id="edx-cust"></div>
        </div>
        <div data-pane="frame" hidden>
          <span class="label">Layout</span>
          <div class="seg" id="edx-layout"><button type="button" data-v="auto" class="on">Auto</button><button type="button" data-v="stacked">Stacked</button><button type="button" data-v="face">Face</button><button type="button" data-v="crop">Crop</button><button type="button" data-v="blur_fit">Blur</button></div>
          <span class="label" style="margin-top:16px">Shots</span>
          <div class="edshots" id="edx-shots"><span class="hint">No shot data. Layout is automatic.</span></div>
        </div>
        <div data-pane="trim" hidden>
          <div class="trimrow">
            <div class="fieldx"><span class="fl">Start (s)</span><input type="number" id="edx-s" step="0.1" min="0"></div>
            <div class="fieldx"><span class="fl">End (s)</span><input type="number" id="edx-e" step="0.1" min="0"></div>
          </div>
          <div class="actions"><button class="btn sm" id="edx-sets">Start ← playhead</button><button class="btn sm" id="edx-sete">End ← playhead</button><button class="btn sm" id="edx-loop">Loop selection</button></div>
        </div>
        <div data-pane="text" hidden><div class="words" id="edx-words" dir="auto"><span class="hint">Loading words…</span></div></div>
      </section>
    </div>
    <section class="card ed-timeline">
      <div class="card-head"><div><h3>Timeline</h3><p class="hint">Waveform and word timing. Drag a word to move it, or drag its edges to trim.</p></div></div>
      <div class="edwave" id="edx-wavebox"><canvas id="edx-wave"></canvas><div id="edx-playhead"></div></div>
      <div class="wtl" id="edx-wtl"></div>
    </section>`;
  $('#edx-tabs').onclick = e => {
    const b = e.target.closest('button'); if (!b) return;
    $$('#edx-tabs button').forEach(x => x.classList.toggle('on', x === b));
    $$('.edside [data-pane]').forEach(pn => pn.hidden = pn.dataset.pane !== b.dataset.tab);
  };
  $('#edx-proj').onchange = e => { const p = state.projects.find(x => x.id === e.target.value); if (p && p.clips.length) edxSelect(p.id, p.clips[0].rank); };
  $('#edx-clip').onchange = e => edxSelect(Edits.pid, +e.target.value);
  $('#edx-undo').onclick = edxUndo; $('#edx-redo').onclick = edxRedo;
  $('#edx-save').onclick = edxSave;
  $('#edx-export').onclick = () => { if (Edits.pid && Edits.rank) openExport(Edits.pid, [Edits.rank], false); };
  $('#edx-acc').onclick = edxAccurate;
  const vEl = $('#edx-v');
  $('#edx-playbtn').onclick = () => { if (vEl.paused) vEl.play().catch(() => {}); else vEl.pause(); };
  vEl.addEventListener('play', () => { paintEdxPlay(true); requestAnimationFrame(edxTick); });
  vEl.addEventListener('pause', () => paintEdxPlay(false));
  vEl.addEventListener('timeupdate', edxTick);
  vEl.addEventListener('seeked', edxTick);
  $('#edx-seek').addEventListener('input', e => { if (vEl.duration) vEl.currentTime = (+e.target.value / 1000) * vEl.duration; });
  $('#edx-sets').onclick = () => { $('#edx-s').value = vEl.currentTime.toFixed(2); edxChanged(); };
  $('#edx-sete').onclick = () => { $('#edx-e').value = vEl.currentTime.toFixed(2); edxChanged(); };
  $('#edx-loop').onclick = () => {                  // the source's own timeline: loop between the trim points
    const c = edxClip(); if (!c) return;
    const s0 = parseFloat($('#edx-s').value), s1 = parseFloat($('#edx-e').value);
    const from = isNaN(s0) ? c.start : s0, to = isNaN(s1) ? c.end : s1;
    const token = Edits.loop = {};                 // one watcher at a time; picking another clip ends it
    vEl.currentTime = from; vEl.play().catch(() => {});
    const watch = () => {                          // checked every frame, so the loop never runs past its end
      if (Edits.loop !== token) return;
      if (!vEl.paused && (vEl.currentTime >= to || vEl.currentTime < from - 0.05)) vEl.currentTime = from;
      requestAnimationFrame(watch);
    };
    watch();
  };
  $('.edside').addEventListener('click', e => { if (e.target.closest('.seg')) { edxSnapshot(); edxDirty(true); edxOverlay(); } });
  $('.edside').addEventListener('change', e => { if (e.target.matches('input,select')) { edxSnapshot(); edxDirty(true); edxOverlay(); } });
  $('#edx-wavebox').addEventListener('click', e => {
    if (!vEl || !vEl.duration) return;
    const r = e.currentTarget.getBoundingClientRect();
    vEl.currentTime = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * vEl.duration;
  });
  document.addEventListener('keydown', edxKeys);
  edxBindOverlay();
  edxDirty(false);
  edxSelect(projs[0].id, projs[0].clips[0].rank);
}
function paintEdxPlay(on) {
  const b = $('#edx-playbtn'); if (!b) return;
  b.innerHTML = ico(on ? 'pause' : 'play', 'fill');
  b.setAttribute('aria-label', on ? 'Pause' : 'Play');
}
function edxProject() { return state.projects.find(x => x.id === Edits.pid); }
function edxClip() { const p = edxProject(); return p?.clips.find(x => x.rank === Edits.rank); }
function edxNote(msg) {
  const n = $('#edx-note'); if (!n) return;
  n.hidden = !msg; n.textContent = msg || '';
}
async function edxSelect(pid, rank) {
  Edits.pid = pid; Edits.rank = rank; Edits.undo = []; Edits.redo = []; Edits.loop = null;
  if (!edxProject()) return;
  $('#edx-proj').value = pid;
  $('#edx-clip').innerHTML = edxProject().clips.map(x => `<option value="${x.rank}" ${x.rank === rank ? 'selected' : ''}>#${x.rank} ${esc(x.title.slice(0, 48))}</option>`).join('');
  try { mergeProject(await api(`/api/projects/${pid}`)); } catch (_) {}   // fresh proxy/video availability
  const p = edxProject(), c = edxClip();
  if (!p || !c) return;
  const v = $('#edx-v');
  if (p.proxy) { mountVideo(v, `/api/projects/${pid}/proxy`, () => edxNote('This preview couldn’t load. Times can still be edited by hand.')); edxNote(''); }
  else if (p.video_id) { mountVideo(v, `/source/${p.video_id}`, () => edxNote('This browser can’t play the source file. Times can still be edited by hand.')); edxNote(''); }
  else { unmountVideo(v); edxNote('Preparing the preview. It appears as soon as the video is ready.'); }
  v.addEventListener('loadedmetadata', () => { try { v.currentTime = c.start; } catch (_) {} }, { once: true });
  $('#edx-s').value = c.start; $('#edx-e').value = c.end;
  const saved = c.style || {};
  $('#edx-preset').value = saved.preset || p.settings.caption_style?.preset || 'bold-pop';
  $('#edx-cust').innerHTML = customizeHTML(saved.overrides || p.settings.caption_style?.overrides, $('#edx-preset').value);
  mountStyles($('.edside'), $('#edx-preset').value);
  const lay = c.framing || 'auto';
  $$('#edx-layout button').forEach(x => x.classList.toggle('on', x.dataset.v === lay));
  paintShots(c);
  try {
    const d = await api(`/api/projects/${pid}/clips/${rank}/transcript?start=${c.start}&end=${c.end}`);
    Edits.words = d.words;
    paintEdxWords();
  } catch (e) { $('#edx-words').innerHTML = `<span class="hint">${esc(e.message)}</span>`; }
  try { Edits.wav = await api(`/api/projects/${pid}/waveform`); paintWave(); } catch (_) {}
  edxOverlay();
  edxSnapshot();
  edxDirty(false);
  editCtx = { pid, rank, t: c.start + 1 };
}
function paintShots(c) {
  const box = $('#edx-shots'); if (!box) return;
  const shots = c.shots || [];
  box.innerHTML = shots.length ? shots.map((s, i) =>
    `<span class="shot">#${i + 1} ${fmtT(s.start)}–${fmtT(s.end)} · ${esc(s.layout || 'auto')}</span>`).join('')
    : '<span class="hint">No shot data. Layout is automatic.</span>';
}
/* Every edit refreshes the caption layer (pvSync), so the Edits overlay is always current. */
function edxOverlay() { pvSync(); }
function edxBindOverlay() {
  if (Edits.overlay) Edits.overlay.destroy();
  Edits.overlay = new PvOverlay({
    host: $('#edx-wrap'), video: $('#edx-v'),
    read: () => { const side = $('.edside'); if (!side) return null; const d = readStyleRoot(side); return { preset: d.preset, ov: d.overrides, captions: true, platform: clipPlatform(edxProject(), edxClip()) }; },
    words: () => Edits.words,
  });
}
function clipPlatform(p, c) {                       // the platform whose caption margin applies: the clip's first export
  return (c && c.platforms && c.platforms[0]) || (p && p.settings && p.settings.platform) || 'shorts';
}
function paintEdxWords() {
  const box = $('#edx-words'); if (!box) return;
  box.innerHTML = '';
  Edits.words.forEach(w => {
    const inp = document.createElement('input');
    inp.value = w.t; inp.dataset.i = w.i; inp.size = Math.max(3, w.t.length); inp.dir = 'auto'; inp.title = fmtT(w.s);
    inp.addEventListener('input', () => { w.t = inp.value; pvSync(); });
    inp.addEventListener('change', () => { w.t = inp.value; edxChanged(); });
    box.appendChild(inp);
  });
  paintEdxWtl();
}
function paintEdxWtl() {
  const tl = $('#edx-wtl'); if (!tl) return;
  const c = edxClip(); if (!c) return;
  const s0 = +$('#edx-s').value || c.start, s1 = +$('#edx-e').value || c.end, span = Math.max(0.1, s1 - s0);
  tl.innerHTML = '';
  Edits.words.forEach(w => {
    const b = document.createElement('div');
    b.className = 'tlb'; b.title = `${w.t} · ${fmtT(w.s)}`;
    b.style.left = Math.max(0, (w.s - s0) / span * 100) + '%';
    b.style.width = Math.max(1.2, (w.e - w.s) / span * 100) + '%';
    tl.appendChild(b);
  });
}
function paintWave() {
  const cv = $('#edx-wave'); if (!cv || !Edits.wav?.peaks?.length) return;
  const dpr = window.devicePixelRatio || 1, W = cv.clientWidth || 600, H = cv.clientHeight || 76;
  cv.width = W * dpr; cv.height = H * dpr;
  const g = cv.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, W, H);
  const peaks = Edits.wav.peaks, n = peaks.length, bw = W / n;
  const accent = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#fff';
  g.fillStyle = accent;
  peaks.forEach((p, i) => { const h = Math.max(1, p * (H - 12)); g.fillRect(i * bw, (H - h) / 2, Math.max(1, bw - 0.5), h); });
}
function edxTick() {
  if (!Edits.active || state.route.name !== 'edits') return;
  const v = $('#edx-v'); if (!v) return;
  if (v.duration) {
    const pct = v.currentTime / v.duration;
    const ph = $('#edx-playhead'); if (ph) ph.style.left = (pct * 100) + '%';
    const sk = $('#edx-seek'); if (sk && document.activeElement !== sk) sk.value = String(Math.round(pct * 1000));
    const tm = $('#edx-time'); if (tm) tm.textContent = `${fmtT(v.currentTime)} / ${fmtT(v.duration)}`;
  }
  if (!v.paused) requestAnimationFrame(edxTick);
}
function edxSnap() {
  const words = {};
  $$('#edx-words input').forEach(i => { words[i.dataset.i] = i.value; });
  return JSON.stringify({
    preset: $('#edx-preset')?.value, overrides: collectOverrides($('.edside')),
    framing: $('#edx-layout .on')?.dataset.v || 'auto',
    trim: [+$('#edx-s').value, +$('#edx-e').value], words,
  });
}
function edxSnapshot() {
  const s = edxSnap();
  const u = Edits.undo;
  if (!u.length || u[u.length - 1] !== s) { u.push(s); if (u.length > 50) u.shift(); }
  Edits.redo = [];
}
function edxRestore(s) {
  const o = JSON.parse(s);
  $('#edx-preset').value = o.preset || 'bold-pop';
  $('#edx-cust').innerHTML = customizeHTML(o.overrides, o.preset);
  mountStyles($('.edside'), o.preset);
  $$('#edx-layout button').forEach(x => x.classList.toggle('on', x.dataset.v === (o.framing || 'auto')));
  $('#edx-s').value = o.trim[0]; $('#edx-e').value = o.trim[1];
  $$('#edx-words input').forEach(i => { if (o.words[i.dataset.i] !== undefined) { i.value = o.words[i.dataset.i]; i.size = Math.max(3, i.value.length); } });
  Edits.words.forEach(w => { if (o.words[w.i] !== undefined) w.t = o.words[w.i]; });
  paintEdxWtl(); edxOverlay();
}
function edxUndo() {
  if (Edits.undo.length < 2) return;
  Edits.redo.push(Edits.undo.pop());
  edxRestore(Edits.undo[Edits.undo.length - 1]);
  edxDirty(true);
}
function edxRedo() {
  const s = Edits.redo.pop();
  if (!s) return;
  Edits.undo.push(s);
  edxRestore(s);
  edxDirty(true);
}
function edxDirty(on) {
  Edits.dirty = !!on;
  const b = $('#ed-dirty'); if (b) b.hidden = !Edits.dirty;
}
function edxChanged() {
  edxSnapshot(); edxDirty(true); edxOverlay();
}
async function edxSave() {
  const btn = $('#edx-save'); btn.disabled = true;
  try {
    const words = {};
    $$('#edx-words input').forEach(i => { words[i.dataset.i] = i.value; });
    const np = await api(`/api/projects/${Edits.pid}/clips/${Edits.rank}`, { method: 'PATCH', body: {
      style: { preset: $('#edx-preset').value, overrides: collectOverrides($('.edside')) },
      framing: $('#edx-layout .on')?.dataset.v || 'auto',
      words } });
    mergeProject(np);
    Edits.undo = []; Edits.redo = []; edxSnapshot(); edxDirty(false);
    toast('Saved', 'ok');
  } catch (e) { toast(e.message, 'bad'); }
  btn.disabled = false;
}
async function edxAccurate() {
  const v = $('#edx-v'); if (!v) return;
  const c = edxClip(); if (!c) return;
  const t = v.currentTime;
  const img = $('#edx-img');
  try {
    const r = await api(`/api/projects/${Edits.pid}/clips/${Edits.rank}/caption-preview`, { method: 'POST', body: {
      t, style: { preset: $('#edx-preset').value, overrides: collectOverrides($('.edside')) } } });
    img.src = r.image; img.hidden = false;
  } catch (e) { toast(e.message, 'bad'); }
}
function edxKeys(e) {
  if (!Edits.active || state.route.name !== 'edits') return;
  const tag = (e.target.tagName || '').toLowerCase();
  if (e.code === 'Space' && !['input', 'textarea', 'select', 'button'].includes(tag)) {
    e.preventDefault();
    const v = $('#edx-v'); if (v) { if (v.paused) v.play().catch(() => {}); else v.pause(); }
  }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z' && !e.shiftKey) { e.preventDefault(); edxUndo(); }
  if ((e.ctrlKey || e.metaKey) && (e.key.toLowerCase() === 'y' || (e.key.toLowerCase() === 'z' && e.shiftKey))) { e.preventDefault(); edxRedo(); }
}
function mergeProject(np) {
  const i = state.projects.findIndex(x => x.id === np.id); if (i >= 0) state.projects[i] = np; else state.projects.unshift(np);
  if (state.route.name === 'project' && state.route.id === np.id) paintProject(np);
  renderSide();
}

/* ----- settings ----- */
function viewSettings() {
  const d = state.settings, s = d.settings, sys = state.system;
  const models = sys?.ollama?.models || [];
  const modelOpts = [...new Set([s.llm.model, ...models])].map(m => `<option ${m === s.llm.model ? 'selected' : ''}>${esc(m)}</option>`).join('');
  const sel = (id, opts, val) => `<select id="${id}">${opts.map(([v, l]) => `<option value="${v}" ${v === val ? 'selected' : ''}>${l}</option>`).join('')}</select>`;
  main.innerHTML = `<header class="page-head">
      <div><div class="eyebrow">Preferences</div><h1 class="page-title">Settings</h1><p class="page-sub">Everything runs on this computer. Changes apply to the next job.</p></div>
      <div class="head-actions"><button class="btn ghost" data-act="reset-settings">Reset to defaults</button><button class="btn primary" data-act="save-settings">${ico('check')}Save settings</button></div>
    </header>
  <div class="set-grid">
      <section class="card">
        <div class="card-head"><h3>System check</h3><button class="btn sm" data-act="recheck">${ico('refresh')}Re-check</button></div>
        <div id="syscheck"></div>
      </section>
      <section class="card">
        <div class="card-head"><div><h3>Transcription</h3><p class="hint">Whisper turns speech into word-level timestamps.</p></div></div>
        <div class="form">
          <div class="field"><span class="fl">Whisper model</span>${sel('s-wmodel', [['auto', 'Auto (recommended)'], ['large-v3-turbo', 'large-v3-turbo (multilingual, fast)'], ['distil-large-v3', 'distil-large-v3 (English, fast)'], ['large-v3', 'large-v3 (best, slower)'], ['medium', 'medium'], ['small', 'small (CPU)']], s.whisper.model)}</div>
          <div class="field"><span class="fl">Device</span>${sel('s-wdev', [['auto', 'Auto (GPU if available)'], ['cuda', 'GPU (CUDA)'], ['cpu', 'CPU']], s.whisper.device)}</div>
          <div class="field"><span class="fl">Language</span>${sel('s-wlang', [['', 'Auto-detect'], ['en', 'English'], ['ar', 'العربية (Arabic)'], ['fr', 'Français'], ['es', 'Español'], ['de', 'Deutsch'], ['it', 'Italiano'], ['pt', 'Português']], s.whisper.language || '')}</div>
          <div class="field"><span class="fl">Accuracy</span>${sel('s-wqual', [['fast', 'Fast'], ['best', 'Best (large-v3 for non-English)']], s.whisper.quality || 'fast')}</div>
          <div class="field full"><p class="hint">The first run downloads the model (about 1–2 GB for turbo). Pre-fetch it to avoid waiting later.</p>
            <div class="actions"><button class="btn sm" data-act="dl-models">${ico('download')}Download models now</button><span class="hint" id="mdl-status"></span></div></div>
        </div>
      </section>
      <section class="card">
        <div class="card-head"><div><h3>AI clip scoring</h3><p class="hint">A local Ollama model judges hook, payoff and clarity.</p></div></div>
        <div class="form">
          <div class="field full">${tog('s-llm', 'Use AI scoring by default', s.llm.enabled)}</div>
          <div class="field"><span class="fl">Ollama address</span><input class="txt" id="s-lhost" value="${esc(s.llm.host)}"></div>
          <div class="field"><span class="fl">Model${models.length ? '' : ' (type a name)'}</span>${models.length ? `<select id="s-lmodel">${modelOpts}</select>` : `<input class="txt" id="s-lmodel" value="${esc(s.llm.model)}">`}</div>
          <div class="field full"><p class="hint">Arabic transcripts use qwen2.5:7b-instruct automatically (<code>ollama pull qwen2.5:7b-instruct</code>).</p></div>
        </div>
      </section>
      <section class="card">
        <div class="card-head"><h3>Data</h3></div>
        <p class="hint">Stored locally in <code class="path">${esc(d.home)}</code>: clips, cached downloads, transcripts and uploads. Marrow ${esc(d.version)}.</p>
        <div class="actions" style="margin-top:14px"><button class="btn" data-act="open-folder">${ico('folder')}Open data folder</button></div>
      </section>
      <section class="card">
        <div class="card-head"><div><h3>YouTube cookies (optional)</h3><p class="hint">Optional. Most videos work without cookies; only set this if YouTube asks for a sign-in check or returns 403. Firefox or Chromium are usually the least trouble: sign in to YouTube in it, then pick it here. A cookies.txt file works with any browser.</p></div></div>
        <div class="form">
          <div class="field"><span class="fl">Use cookies from browser</span>${sel('s-cookie', [['', 'None'], ['chromium', 'Chromium'], ['firefox', 'Firefox'], ['chrome', 'Chrome'], ['edge', 'Edge'], ['brave', 'Brave'], ['safari', 'Safari']], s.cookies?.from_browser || '')}</div>
          <div class="field"><span class="fl">…or a cookies.txt file</span><input class="txt" id="s-cookiefile" placeholder="C:\\cookies.txt" value="${esc(s.cookies?.cookiefile || '')}"></div>
          <div class="field full"><p class="hint">Sign in to YouTube in that browser first. Chromium, Chrome and Edge lock their cookie database while open. If you see “could not copy cookie database”, close the browser or export a cookies.txt file. If the saved browser isn't installed, Marrow retries without browser cookies.</p></div>
        </div>
      </section>
      <section class="card">
        <div class="card-head"><h3>Rendering &amp; captions</h3></div>
        <div class="form">
          <div class="field"><span class="fl">Video encoder</span>${sel('s-enc', [['auto', 'Auto (recommended)'], ['h264_nvenc', 'NVIDIA GPU (NVENC), faster'], ['libx264', 'CPU (libx264), works everywhere']], s.render.encoder)}</div>
          <div class="field"><span class="fl">Caption font fallback</span><input class="txt" id="s-font" value="${esc(s.captions.font)}"></div>
          <div class="field full">${tog('s-loud', 'Normalize loudness', s.render.loudnorm, 'About −16 LUFS, so clips sit at a consistent volume.')}</div>
        </div>
      </section>
      <section class="card">
        <div class="card-head"><h3>Appearance &amp; alerts</h3></div>
        <div class="form">
          <div class="field"><span class="fl">Theme</span><div class="seg" id="themeSeg"><button type="button" data-t="dark">Dark</button><button type="button" data-t="light">Light</button><button type="button" data-t="system">System</button></div></div>
          <div class="field"><span class="fl">Accent</span><div class="seg grid2" id="accentSeg"><button type="button" data-a="graphite">Graphite</button><button type="button" data-a="blue">Blue</button><button type="button" data-a="green">Green</button><button type="button" data-a="orange">Orange</button></div></div>
          <div class="field"><span class="fl">Caption pace</span><div class="seg tight" id="paceSeg"><button type="button" data-p="0.28">Relaxed</button><button type="button" data-p="0.22">Normal</button><button type="button" data-p="0.16">Snappy</button></div></div>
          <div class="field">
            <span class="fl">Alerts</span>
            <label class="tog"><input type="checkbox" id="soundTog"><span class="knob"></span><span class="tl">Sound when clips are ready<small>A short chime and a tab-title update.</small></span></label>
            <div class="actions" style="margin-top:10px"><button class="btn sm ghost" data-act="test-beep">${ico('play', 'fill')}Test sound</button></div>
          </div>
        </div>
      </section>
  </div>`;
  paintSysCheck();
  const curT = document.documentElement.dataset.themeChoice || 'system';
  $$('#themeSeg button').forEach(x => x.classList.toggle('on', x.dataset.t === curT));
  const curA = document.documentElement.dataset.accent || 'graphite';
  $$('#accentSeg button').forEach(x => x.classList.toggle('on', x.dataset.a === curA));
  $('#themeSeg').onclick = e => { const b = e.target.closest('button'); if (!b) return;
    $$('#themeSeg button').forEach(x => x.classList.toggle('on', x === b)); setTheme(b.dataset.t); };
  $('#accentSeg').onclick = e => { const b = e.target.closest('button'); if (!b) return;
    $$('#accentSeg button').forEach(x => x.classList.toggle('on', x === b)); setAccent(b.dataset.a); };
  const st = $('#soundTog'); if (st) { st.checked = soundOn(); st.onchange = () => { try { localStorage.setItem('soundFinish', st.checked ? 'on' : 'off'); } catch (_) {} }; }
  const pace = String(s.captions.min_gap ?? '0.22');
  $$('#paceSeg button').forEach(x => x.classList.toggle('on', x.dataset.p === pace || (+x.dataset.p === +pace)));
  $('#paceSeg').onclick = e => { const b = e.target.closest('button'); if (!b) return;
    $$('#paceSeg button').forEach(x => x.classList.toggle('on', x === b)); };
}
function paintSysCheck() {
  const box = $('#syscheck'); if (!box) return; const s = state.system;
  if (!s) { box.textContent = 'Checking…'; return; }
  const row = (cls, t, d) => `<div class="chk"><span class="dot ${cls}"></span><span><span class="t">${t}</span> <span class="d">${d}</span></span></div>`;
  // YouTube setup: the four checks that decide whether a "not a bot" error can be fixed here.
  const yt = s.ytdlp || {}, ck = s.cookies || {};
  const ytRow = yt.version
    ? row(yt.new_enough ? 'ok' : 'warn', 'yt-dlp', `${esc(yt.version)} · ${yt.new_enough ? 'new enough for YouTube' : 'too old for YouTube: run pip install -U "yt-dlp[default,deno]"'}`)
    : row('bad', 'yt-dlp', yt.error ? esc(yt.error) : 'not installed: pip install -U "yt-dlp[default,deno]"');
  box.innerHTML = row(s.ffmpeg ? 'ok' : 'bad', 'FFmpeg', s.ffmpeg ? 'found' : 'not found — install it and restart Marrow') +
    ytRow +
    row(yt.js_runtime ? 'ok' : 'warn', 'JavaScript runtime', yt.js_runtime ? `${esc(yt.js_runtime)} found` : 'none. YouTube needs one: pip install deno, or install Node.js') +
    row(yt.solver ? 'ok' : 'warn', 'YouTube solver', yt.solver ? 'yt-dlp-ejs installed' : 'missing: pip install -U "yt-dlp[default]"') +
    row(ck.ok ? 'ok' : (ck.source === 'none' ? 'warn' : 'bad'), 'YouTube cookies', esc(ck.message || 'not checked')) +
    row(s.gpu ? 'ok' : 'warn', 'Whisper on GPU', s.gpu ? 'working' : 'failed — ' + esc(s.gpu_error || 'no CUDA GPU') + ' (transcription uses the CPU)') +
    row(s.encoder === 'h264_nvenc' ? 'ok' : '', 'Encoder', s.encoder === 'h264_nvenc' ? 'NVENC (GPU)' : 'libx264 (CPU)') +
    row(s.libass === false ? 'warn' : 'ok', 'ASS captions', s.libass === false ? 'libass filter not found in FFmpeg — captions may not render' : 'libass available') +
    row(s.ollama.reachable ? 'ok' : 'warn', 'Ollama', s.ollama.reachable ? 'running at ' + esc(s.ollama.host) : 'not reachable at ' + esc(s.ollama.host) + ' — AI scoring will be skipped') +
    row(s.ollama.model_ready ? 'ok' : (s.ollama.reachable ? 'warn' : ''), 'Model “' + esc(s.ollama.model) + '”', s.ollama.model_ready ? 'ready' : 'not pulled — run: ollama pull ' + esc(s.ollama.model)) +
    (s.gpu ? '' : row('', 'GPU pip packages', 'for GPU speed run: pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"'));
}
function readSettings() {
  return {
    whisper: { model: $('#s-wmodel').value, device: $('#s-wdev').value, language: $('#s-wlang').value, quality: $('#s-wqual').value },
    llm: { enabled: $('[data-opt="s-llm"]').checked, host: $('#s-lhost').value.trim(), model: $('#s-lmodel').value.trim() },
    render: { encoder: $('#s-enc').value, loudnorm: $('[data-opt="s-loud"]').checked },
    captions: { font: $('#s-font').value.trim(), min_gap: +($('#paceSeg .on')?.dataset.p || 0.22) },
    cookies: { from_browser: $('#s-cookie').value, cookiefile: $('#s-cookiefile').value.trim() } };
}

/* ---------- actions (event delegation) ---------- */
const actions = {
  async go() { await startProject(); },
  seg(b) { $$('button', b.parentElement).forEach(x => x.classList.toggle('on', x === b));
    if (b.parentElement.dataset.ov) b.parentElement.dataset.touched = '1';
    const scope = b.closest('.optbody,.modal,#styleCard'); if (scope && $('.styleGrid', scope)) previewReal(scope);
    if (b.closest('#optbox')) paintPlan();
    if (b.closest('#styleCard,#optbox,.custwrap')) capChanged(); },
  'cust-reset'(b) {                                   // back to the preset: no overrides at all
    const wrap = b.closest('.custwrap'); if (!wrap) return;
    const scope = wrap.closest('.optbody,.modal,#styleCard,.edside') || document;
    const edits = !!wrap.closest('.edside');
    if (edits) edxSnapshot();
    wrap.innerHTML = customizeHTML({}, $('.stylePreset', scope)?.value || 'bold-pop');
    previewReal(scope);
    if (edits) { edxDirty(true); edxOverlay(); }
    capChanged();
  },
  'rm-upload'() { clearPending(); resetFound(); },
  async cancel() {
    try { mergeProject(await api(`/api/projects/${curProject().id}/cancel`, { method: 'POST', body: {} })); toast('Cancelling…'); } catch (e) { toast(e.message, 'bad'); }
  },
  regen() {
    const p = curProject();
    const m = openModal(`<h3>${p.status === 'done' ? 'Regenerate clips' : 'Try again'}</h3><p class="desc">Run the pipeline again with these settings. The download and transcript are cached, so this is much faster than the first run. Existing clips are replaced when it finishes.</p>
      <div id="rg-opts" style="margin:0 -18px">${optsPanel(p.settings)}</div><div class="mfoot"><button class="btn ghost" id="rg-no">Cancel</button><button class="btn primary" id="rg-go">Start</button></div>`);
    mountStyles(m, p.settings.caption_style?.preset || 'bold-pop');
    $$('details.cust', m).forEach(d => { d.open = custOpen; });
    $('#rg-no', m).onclick = closeModal;
    $('#rg-go', m).onclick = async () => {
      try { const np = await api(`/api/projects/${p.id}/regenerate`, { method: 'POST', body: { settings: readOpts(m) } }); closeModal(); mergeProject(np); location.hash = '#/p/' + p.id; viewProject(); }
      catch (e) { toast(e.message, 'bad'); }
    };
  },
  async 'del-project'() {
    const p = curProject();
    const r = await confirmBox({ title: 'Delete this project?', text: `“${p.name}” and its exported clips will be removed from your disk.`, ok: 'Delete', danger: true, check: 'Also delete the cached download, transcript and uploaded file (frees disk space)' });
    if (!r.ok) return;
    try { await api(`/api/projects/${p.id}?purge=${r.checked ? 1 : 0}`, { method: 'DELETE' }); state.projects = state.projects.filter(x => x.id !== p.id); toast('Project deleted', 'ok'); location.hash = '#/projects'; }
    catch (e) { toast(e.message, 'bad'); }
  },
  async rename() {
    const p = curProject();
    const m = openModal(`<h3>Rename project</h3><div class="field" style="margin-top:12px"><input class="txt" id="rn" maxlength="120" value="${esc(p.name)}"></div><div class="mfoot"><button class="btn ghost" id="rn-no">Cancel</button><button class="btn primary" id="rn-go">Save</button></div>`);
    const go = async () => { try { mergeProject(await api(`/api/projects/${p.id}`, { method: 'PATCH', body: { name: $('#rn', m).value } })); closeModal(); } catch (e) { toast(e.message, 'bad'); } };
    $('#rn-no', m).onclick = closeModal; $('#rn-go', m).onclick = go; $('#rn', m).addEventListener('keydown', e => { if (e.key === 'Enter') go(); }); $('#rn', m).select();
  },
  async 'open-folder'() {
    try { const d = await api('/api/open-folder', { method: 'POST', body: { project: state.route.name === 'project' ? state.route.id : null } }); toast('Opened ' + d.path, 'ok'); }
    catch (e) { toast(e.message, 'bad'); }
  },
  'clip-plat'(b) {
    const { el, c } = clipOf(b); const pl = b.dataset.plat; el.dataset.plat = pl;
    $$('.plat-seg button', el).forEach(x => x.classList.toggle('on', x === b));
    const v = $('video', el); const t = v.currentTime, was = !v.paused;
    v.src = c.urls[pl];
    v.addEventListener('loadedmetadata', () => { v.currentTime = t; if (was) v.play().catch(() => {}); }, { once: true });
  },
  'copy-title'(b) { copyText(clipOf(b).c.title, 'Title copied'); const m = b.closest('details'); if (m) m.removeAttribute('open'); },
  'copy-tags'(b) { copyText(clipOf(b).c.hashtags.map(t => '#' + t).join(' '), 'Hashtags copied'); const m = b.closest('details'); if (m) m.removeAttribute('open'); },
  'export-clip'(b) { const { p, c } = clipOf(b); openExport(p.id, [c.rank], false); },
  'download-clip'(b) { const { p, c, el } = clipOf(b); downloadClip(p.id, el?.dataset.plat || c.platforms[0], c); },
  'lock-proj'(b) { toggleLock(b.dataset.id); },
  'export-all'() { const p = curProject(); openExport(p.id, p.clips.map(c => c.rank), true); },
  'copy-error'(b) { copyText(curProject().error || 'Unknown error', 'Error details copied'); },
  'go-settings'() { location.hash = '#/settings'; },
  'toggle-analysis'() {
    localStorage.setItem('hideScan', localStorage.getItem('hideScan') === '1' ? '0' : '1');
    const p = curProject(); if (p) paintProject(p, true);
  },
  'copy-caption'(b) {
    const { c } = clipOf(b);
    copyText(`${c.title}\n${(c.hashtags || []).map(t => '#' + t).join(' ')}`.trim(), 'Caption copied');
    const m = b.closest('details'); if (m) m.removeAttribute('open');
  },
  'clear-source'() {
    clearPending(); resetFound();
    const u = $('#url'); if (u) u.value = ''; state.url = '';
  },
  'generate-anyway'() { startProject(); },
  'view-clip'(b) {
    const { el, p, c } = clipOf(b);
    const ready = p.clips.filter(x => x.status !== 'rendering' && x.urls && x.urls[x.platforms[0]]);
    const list = ready.map(x => { const pl = (x.rank === c.rank && el.dataset.plat) || x.platforms[0];
      return { pid: p.id, rank: x.rank, url: x.urls[pl], download: x.urls[pl] + '&download=1', title: x.title }; });
    Viewer.open(list, Math.max(0, ready.findIndex(x => x.rank === c.rank)));
  },
  'edit-clip'(b) { const { p, c } = clipOf(b); openEdit(p, c); },
  'subs-clip'(b) { const { p, c } = clipOf(b); openEdit(p, c, 'caps'); },
  async 'del-clip'(b) {
    const { p, c } = clipOf(b);
    const r = await confirmBox({ title: 'Delete this clip?', text: `“${c.title}” will be removed from your disk.`, ok: 'Delete clip', danger: true });
    if (!r.ok) return;
    try { mergeProject(await api(`/api/projects/${p.id}/clips/${c.rank}`, { method: 'DELETE' })); toast('Clip deleted', 'ok'); } catch (e) { toast(e.message, 'bad'); }
  },
  async recheck() { $('#syscheck').textContent = 'Checking…'; await refreshSystem(true); paintSysCheck(); toast('Checked'); },
  'theme-toggle'() { setTheme(document.documentElement.dataset.theme === 'light' ? 'dark' : 'light'); },
  'test-beep'() { ac(); doneBeep(); toast('Beep'); },
  async 'dl-models'(b) {
    const st = $('#mdl-status'); b.disabled = true;
    try {
      await api('/api/models/download', { method: 'POST', body: {} });
      const poll = setInterval(async () => {
        try {
          const d = await api('/api/models/download');
          st.textContent = d.running ? `Downloading… ${d.done.join(', ')}` : (d.error ? `Failed: ${d.error}` : `Done: ${d.done.join(', ')}`);
          if (!d.running) { clearInterval(poll); b.disabled = false; toast(d.error ? d.error : 'Models downloaded', d.error ? 'bad' : 'ok'); }
        } catch (_) { clearInterval(poll); b.disabled = false; }
      }, 2000);
    } catch (e) { toast(e.message, 'bad'); b.disabled = false; }
  },
  async 'save-settings'() {
    try { state.settings = await api('/api/settings', { method: 'PUT', body: readSettings() }); state.opts = null; await refreshSystem(); viewSettings(); toast('Settings saved', 'ok'); }
    catch (e) { toast(e.message, 'bad'); }
  },
  async 'reset-settings'() {
    const r = await confirmBox({ title: 'Reset settings?', text: 'Restores the defaults from config.yaml.', ok: 'Reset' }); if (!r.ok) return;
    try { state.settings = await api('/api/settings', { method: 'PUT', body: {} }); state.opts = null; await refreshSystem(); viewSettings(); toast('Settings reset', 'ok'); } catch (e) { toast(e.message, 'bad'); }
  },
};
/* Edits: guard against losing unsaved work (capture phase, before navigation) */
document.addEventListener('click', e => {
  const a = e.target.closest?.('a[href^="#/"]');
  if (a && typeof Edits !== 'undefined' && Edits.dirty && Edits.active) {
    if (!window.confirm('Discard unsaved edits?')) { e.preventDefault(); e.stopPropagation(); return; }
    Edits.dirty = false;
  }
}, true);
document.addEventListener('click', e => {
  const b = e.target.closest('[data-act]'); if (!b || b.tagName === 'A' && b.dataset.act === 'dl') return;
  const fn = actions[b.dataset.act]; if (fn) { e.preventDefault(); fn(b); }
});
// dropping a file anywhere should upload it (never navigate away to the file)
window.addEventListener('dragover', e => e.preventDefault());
window.addEventListener('drop', e => {
  e.preventDefault(); const f = e.dataTransfer?.files?.[0]; if (!f) return;
  if (state.route.name !== 'home') { location.hash = '#/'; setTimeout(() => handleFile(f), 50); } else handleFile(f);
});

/* ---------- router & polling ---------- */
function parseRoute() {
  const h = location.hash.replace(/^#\/?/, '');
  if (h.startsWith('p/')) return { name: 'project', id: h.slice(2) };
  if (h === 'projects') return { name: 'projects' };
  if (h === 'settings') return { name: 'settings' };
  if (h === 'edits') return { name: 'edits' };
  return { name: 'home' };
}
async function render() {
  const t0 = performance.now();
  state.route = parseRoute(); closeModal(); renderSide();
  if (state.route.name !== 'home') stopPolling();          // the fetched video is kept and repainted on return
  try {
    if (state.route.name === 'home') viewHome();
    else if (state.route.name === 'projects') viewProjects();
    else if (state.route.name === 'project') viewProject();
    else if (state.route.name === 'edits') viewEdits();
    else if (state.route.name === 'settings') {
      if (state.settings && state.system) {
        viewSettings();   // instant from cache, then revalidate in parallel
        Promise.allSettled([refreshSystem(), api('/api/settings').then(s => { state.settings = s; })])
          .then(() => { if (state.route.name === 'settings') viewSettings(); });
      } else {
        await refreshSystem();
        try { state.settings = await api('/api/settings'); } catch (e) { toast(e.message, 'bad'); return; }
        if (state.route.name === 'settings') viewSettings();
      }
    }
  } catch (e) {
    console.error(e);
    main.innerHTML = `<div class="empty">This view failed to render.<br><span class="note">${esc(e.message || e)}</span><br><br><a class="btn sm" href="#/">Back to Home</a></div>`;
  }
  window.scrollTo(0, 0);
  console.debug(`[perf] route ${state.route.name}: ${Math.round(performance.now() - t0)} ms`);
}
window.addEventListener('hashchange', render);
document.addEventListener('visibilitychange', () => {
  document.body.classList.toggle('tabhidden', document.visibilityState !== 'visible');
});
async function refresh() {
  try {
    const keep = new Map(state.projects.map(p => [p.id, { log: p.log, logTotal: p.logTotal }]));
    state.projects = (await api('/api/projects')).projects;
    state.projects.forEach(p => { const k = keep.get(p.id); if (k && k.log) { p.log = k.log; p.logTotal = k.logTotal; } });
  } catch (_) { return; }
  renderSide();
  const r = state.route.name;
  if (r === 'home') paintRecent(); else if (r === 'projects') paintProjects();
  else if (r === 'project') { const p = curProject(); if (p) refreshProject(p.id); }
}
setInterval(() => { if (document.hidden) return; if (hasActive()) refresh(); }, 1500);
setInterval(() => { if (!document.hidden && !hasActive()) refresh(); }, 15000);
(async function init() {
  state.route = parseRoute();
  const saved = loadFound();
  if (saved && saved.url && saved.probeId) { Home.url = saved.url; Home.probeId = saved.probeId; state.url = saved.url; }
  const [p, s, sys] = await Promise.allSettled([api('/api/projects'), api('/api/settings'), api('/api/system')]);
  if (p.status === 'fulfilled') state.projects = p.value.projects;
  if (s.status === 'fulfilled') state.settings = s.value;
  if (sys.status === 'fulfilled') state.system = sys.value;
  render();
})();
