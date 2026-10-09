"""Headless-Chromium check of the caption layer over the real video: the Edits page and the Edit modal.

The captions there must be the captions the renderer burns in: the same words, the same lit word (or word group)
at every moment, the same emphasis, and the page's own clock must drive them (no offset from the clip start).
The expectation is captioner.generate_ass on the same transcript, parsed back into events. Editing a control must
not reach the server. Needs: pip install playwright && python -m playwright install chromium, and ffmpeg (to make a
short test video). Skips when either is missing. The server under test runs on a temp home (no user data).
"""
import json
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from marrow import captioner, studio  # noqa: E402  (the reference is the renderer's own code)
from marrow import server as S  # noqa: E402

PORT = 18785
ROOT = Path(__file__).resolve().parents[1]
PID, VID = "a1b2c3d4e5", "fxvid"
CLIP = (5.0, 25.0)
SAMPLE_STEP = 0.2

EN = ["This is the moment everything changed,", "nobody expected it.", "Watch what happens next!",
      "Unbelievable results in seconds,", "so keep going;", "the best part is still coming.",
      "Trust the process and stay focused", "because consistency beats talent."]

# the page reads the video's own clock; these run in the page
SAMPLER_JS = """async ({ ref, hostSel, videoSel, step, playSeconds }) => {
  const v = document.querySelector(videoSel);
  const seek = t => new Promise(res => {
    if (Math.abs(v.currentTime - t) < 1e-3) return res();
    let to = 0;
    const done = () => { clearTimeout(to); v.removeEventListener('seeked', done); res(); };
    to = setTimeout(done, 2000); v.addEventListener('seeked', done); v.currentTime = t;
  });
  const readCap = () => {
    const cap = document.querySelector(hostSel);
    if (!cap || cap.hidden) return { kind: 'none' };
    const solo = cap.querySelector('.pv-solo');
    if (solo) return { kind: 'word', text: solo.textContent };
    const ws = Array.from(cap.querySelectorAll('.pv-w'));
    if (!ws.length) return { kind: 'none' };
    const li = ws.findIndex(w => w.classList.contains('pv-on'));
    const lw = li >= 0 ? ws[li] : null;
    return { kind: 'line', text: ws.map(w => w.textContent).join(' '), lit: li,
             scale: lw ? Math.round(parseFloat(lw.style.getPropertyValue('--sc')) * 100) : null };
  };
  const expectAt = t => { for (const e of ref.events) if (t >= e.s && t < e.e) return e; return null; };
  const edge = t => ref.events.some(e => Math.abs(e.s - t) < 0.035 || Math.abs(e.e - t) < 0.035);
  const same = (e, d) => {
    if (!e) return d.kind === 'none';
    if (e.kind === 'word') return d.kind === 'word' && d.text === e.text;
    return d.kind === 'line' && d.text === e.text && d.lit === e.lit && d.scale === e.scale;
  };
  const out = { samples: 0, lines: 0, words: 0, nones: 0, mismatches: 0, bad: [] };
  for (let t = 0.04; t < ref.clip_end - ref.clip_start; t += step) {
    await seek(ref.clip_start + t);
    if (edge(t)) continue;
    const d = readCap(), e = expectAt(t);
    out.samples++;
    if (!e) out.nones++; else if (e.kind === 'word') out.words++; else out.lines++;
    if (!same(e, d)) { out.mismatches++; if (out.bad.length < 4) out.bad.push({ t: +t.toFixed(2), want: e && e.text, got: d }); }
  }
  if (playSeconds) {                               // while the video plays, the caption follows each frame
    await seek(ref.clip_start);
    const rec = [];
    v.play();
    const t0 = performance.now();
    await new Promise(res => {
      const f = () => {
        rec.push({ t: v.currentTime, d: readCap() });
        if (performance.now() - t0 < playSeconds * 1000 && !v.paused) requestAnimationFrame(f); else res();
      };
      requestAnimationFrame(f);
    });
    v.pause();
    out.playback = { frames: rec.length, mismatches: 0 };
    for (const r of rec) {
      const trel = r.t - ref.clip_start;
      if (trel < 0 || edge(trel)) continue;
      if (!same(expectAt(trel), r.d)) out.playback.mismatches++;
    }
  }
  return out;
}"""

# sets the caption controls the way a user does, inside a scope
APPLY_JS = """({ acts, scope }) => {
  const fire = el => { el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); };
  for (const a of acts) {
    if (a.preset) document.querySelector(`${scope} .scard[data-k="${a.preset}"]`).click();
    else if (a.seg) document.querySelector(`${scope} [data-ov="${a.seg[0]}"] button[data-v="${a.seg[1]}"]`).click();
    else if (a.check) { const el = document.querySelector(`${scope} input[data-ov="${a.check[0]}"]`); el.checked = a.check[1]; fire(el); }
  }
}"""

CASES = {
    "bold-pop": {"acts": [], "style": {"preset": "bold-pop", "overrides": {}}},
    "hormozi-words": {"acts": [{"preset": "hormozi"}, {"seg": ["display", "word"]}, {"check": ["strip_punct", False]}],
                      "style": {"preset": "hormozi", "overrides": {"display": "word", "strip_punct": False}}},
}


def _ffmpeg():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _ass_time(s):
    h, m, rest = s.split(":")
    return int(h) * 3600 + int(m) * 60 + float(rest)


def _events(ass_path):
    """The renderer's Dialogue events: line or word-group text, and the lit word (index, text, scale)."""
    events = []
    for line in Path(ass_path).read_text(encoding="utf-8").splitlines():
        if not line.startswith("Dialogue:"):
            continue
        parts = line.split(",", 9)
        s, e, body = _ass_time(parts[1]), _ass_time(parts[2]), parts[9]
        kind, lit, widx, lit_flag, after_lit, lit_text, lit_scale, plain = "line", -1, -1, False, False, None, None, []
        for tok in re.findall(r"\{[^}]*\}|[^{}]+", body):
            if tok.startswith("{"):
                if r"\t(0,90," in tok:
                    kind = "word"
                if after_lit:
                    after_lit = False
                    continue
                if r"\fscx" in tok:
                    m = re.search(r"\\t\(0,110,\\fscx(\d+)", tok) or re.search(r"\\fscx(\d+)", tok)
                    lit_scale, lit_flag = int(m.group(1)), True
                continue
            plain.append(tok)
            if lit_flag and tok.strip():
                lit, lit_text, lit_flag, after_lit = widx + 1, tok, False, True
                widx += 1
            else:
                widx += len(tok.split())
        events.append({"s": round(s, 3), "e": round(e, 3), "kind": kind, "text": "".join(plain),
                       "lit": lit, "scale": lit_scale if (kind == "line" and lit >= 0) else None})
    return sorted(events, key=lambda x: x["s"])


@pytest.fixture(scope="module")
def home():
    ff = _ffmpeg()
    if not ff:
        pytest.skip("ffmpeg not available for the test video")
    h = Path(tempfile.mkdtemp(prefix="marrow_overlay_"))
    src = h / "source.webm"
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=25",
                    "-t", "32", "-c:v", "libvpx", "-b:v", "200k", "-deadline", "realtime", "-cpu-used", "8", "-an", str(src)],
                   check=True, timeout=180)
    rng = random.Random(7)
    words, t = [], 0.6
    for k in range(len(EN) * 2):
        for w in EN[k % len(EN)].split():
            d = rng.uniform(0.22, 0.55) + (0.25 if len(w) > 9 else 0)
            words.append([round(t, 2), round(t + d, 2), w])
            t += d + (rng.uniform(0.02, 0.12) if rng.random() < 0.8 else rng.uniform(0.38, 0.5))
        t += rng.uniform(0.7, 1.4) if k % 2 == 0 else rng.uniform(0.2, 0.5)
    words = [w for w in words if w[1] < 30]
    work = h / "work" / VID
    work.mkdir(parents=True)
    (work / "words.json").write_text(json.dumps({"words": words}, ensure_ascii=False), encoding="utf-8")
    import numpy as np
    base = np.array([rng.uniform(0.05, 0.35) for _ in range(int(30 * 16000 / 512) + 50)])
    for s, e, _ in words:
        a, b = int(s * studio.ENERGY_FPS), max(int(s * studio.ENERGY_FPS) + 1, int(e * studio.ENERGY_FPS))
        if rng.random() < 0.3:
            base[a:b] = np.maximum(base[a:b], rng.uniform(0.7, 1.0))
    np.save(work / "energy.npy", base)
    proj = {"id": PID, "name": "Overlay fixture", "source": str(src), "source_kind": "file", "status": "done",
            "stage": "", "progress": 1.0, "created": 0, "started": 0, "finished": 1, "error": None, "video_id": VID,
            "settings": S.clean_job_settings(None), "locked": False,
            "clips": [{"rank": 1, "start": CLIP[0], "end": CLIP[1], "duration": CLIP[1] - CLIP[0], "score": 0.9,
                       "title": "Clip", "reason": "", "hashtags": [], "status": "ready",
                       "files": {"shorts": "clip1.mp4"}, "thumb": None, "style": None, "shots": None, "rev": 1}]}
    (h / "projects.json").write_text(json.dumps([proj]), encoding="utf-8")
    return h


@pytest.fixture(scope="module")
def server(home):
    proc = subprocess.Popen([sys.executable, "-m", "marrow.server", "--port", str(PORT), "--no-browser", "--home", str(home)],
                            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    deadline = time.time() + 90
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://localhost:{PORT}/", timeout=3)
            break
        except Exception:
            time.sleep(1)
    yield f"http://localhost:{PORT}"
    proc.terminate()


def _reference(home, name):
    work = home / "work" / VID
    words, _raw = studio.load_words(work)
    studio.attach_energy(work, words)
    out = home / f"{name}.ass"
    captioner.generate_ass(words, CLIP[0], CLIP[1], out, CASES[name]["style"], 1080, 1920, 420)
    return {"clip_start": CLIP[0], "clip_end": CLIP[1], "events": _events(out)}


def test_edits_and_edit_modal_show_the_renderers_captions(server, home):
    from playwright.sync_api import sync_playwright

    refs = {name: _reference(home, name) for name in CASES}
    assert sum(1 for e in refs["bold-pop"]["events"] if e["kind"] == "line") > 20   # the fixture has real content
    errors, api = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("request", lambda r: api.append(r.url) if "/api/" in r.url else None)

        def fresh(hash_):
            page.goto("about:blank")
            page.goto(f"{server}/{hash_}", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof state !== 'undefined' && state.projects && state.projects.length > 0")

        for name, case in CASES.items():
            fresh("#/edits")
            page.wait_for_function("() => document.querySelector('#edx-v') && document.querySelector('#edx-v').readyState >= 1"
                                   " && Edits.words.length > 0", timeout=30000)
            page.wait_for_timeout(600)                        # let the page finish its own requests first
            api.clear()
            page.evaluate(APPLY_JS, {"acts": case["acts"], "scope": ".edside"})
            page.wait_for_timeout(250)
            assert api == [], f"a control change reached the server: {api}"   # overlay edits are client-side only
            res = page.evaluate(SAMPLER_JS, {"ref": refs[name], "hostSel": "#edx-wrap > .pv-cap", "videoSel": "#edx-v",
                                             "step": SAMPLE_STEP, "playSeconds": 1.5 if name == "bold-pop" else 0})
            assert res["mismatches"] == 0, (name, res["bad"])
            assert res["samples"] > 60 and res["lines" if name == "bold-pop" else "words"] > 20, (name, res)
            if name == "bold-pop":
                assert res["playback"]["mismatches"] == 0, res["playback"]

        # Start <- playhead uses the video's own time, and the Edit modal's real-frame time is that same time
        fresh("#/edits")
        page.wait_for_function("() => document.querySelector('#edx-v').readyState >= 1 && Edits.words.length > 0", timeout=30000)
        page.wait_for_timeout(600)
        start = page.evaluate("""async () => {
          const v = document.querySelector('#edx-v');
          v.currentTime = 15.0; await new Promise(r => v.addEventListener('seeked', r, { once: true }));
          document.querySelector('#edx-sets').click();
          return document.querySelector('#edx-s').value;
        }""")
        assert float(start) == pytest.approx(15.0, abs=0.01)

        page.evaluate("""() => { const p = state.projects.find(x => x.id === 'a1b2c3d4e5'); openEdit(p, p.clips[0], 'trim'); }""")
        page.wait_for_function("() => document.querySelectorAll('#ed-words input').length > 0 && document.querySelector('#ed-src').readyState >= 1",
                               timeout=30000)
        page.evaluate("() => document.querySelector('#modal-root .tabs button[data-tab=\"trim\"]').click()")
        page.wait_for_timeout(200)
        res = page.evaluate(SAMPLER_JS, {"ref": refs["bold-pop"], "hostSel": "#modal-root .livewrap > .pv-cap",
                                         "videoSel": "#ed-src", "step": 0.4, "playSeconds": 0})
        assert res["mismatches"] == 0, res["bad"]
        assert res["lines"] > 10, res
        real = page.evaluate("""async () => {
          const v = document.querySelector('#ed-src');
          v.currentTime = 21.0; await new Promise(r => v.addEventListener('seeked', r, { once: true }));
          await new Promise(r => setTimeout(r, 100));
          return { video: v.currentTime, frame: editCtx && editCtx.t };
        }""")
        assert real["frame"] == pytest.approx(real["video"], abs=0.01)
        browser.close()
    assert errors == []
